# Design

Margin reviews Python code (and JavaScript, TypeScript, Java and Go more lightly) by combining
deterministic static analysis with review by hosted LLMs, and shows every finding with where it came
from. This document is the overview; each stage has its own document, linked below.

## 1. Goals

- **Find real problems:** bugs, vulnerabilities (with CWE ids), style deviations and performance
  issues, including the semantic ones no rule can express.
- **Be checkable:** every finding cites real lines and quotes real code; every AI claim says which
  model made it and which confirmed it; the quality score shows its formula.
- **Work on free tiers:** rate limits, quotas and outages are the normal case, not an error.
- **Treat uploads as hostile:** never execute uploaded code, never let an upload's configuration hide
  findings, and send no code to a hosted model without consent or with secrets in it.

Non-goals for this version: applying fixes automatically, and reasoning across files beyond the imports
and signatures shown with each chunk.

## 2. Architecture

```
 upload / directory ──► ingest ──► preprocess ──► static analysis ──► review ──► verify ──► summarize ──► report
   (.zip, file, dir)   safe unzip   language,     Ruff · Bandit ·      chunk +    second      executive     score,
                       filters,     tree-sitter,  mypy · Radon ·       static     model on    summary       HTML,
                       limits       chunks ≤ 500  Vulture · Lizard ·   context    serious                   JSON,
                                    lines         detect-secrets ·     → models   AI findings               SARIF
                                                  Opengrep
                                                        │                  │
                                                        ▼                  ▼
                                               one Finding schema    LLM router ── Gemini · NVIDIA NIM ·
                                                                     (limits, breakers,  Hugging Face · local
                                                                      fallback, cache,
                                                                      consent)
```

The same pipeline (`app/pipeline.py`) serves every interface: the **CLI** (`margin scan`), the **web
API** with live server-sent events, the **web UI** built on that API, and the **GitHub Action** that
runs the CLI and uploads SARIF. Only the ingest step and the event sink differ.

## 3. Stages

| Stage | What happens | Details |
|---|---|---|
| Ingest | Archives are extracted through one hardened path: no absolute paths, `..`, symlinks or special files; caps of 20 MB compressed, 80 MB uncompressed, 2,000 files, a 100:1 compression ratio and 1 MB per file. Dependencies, build output, lockfiles, minified and binary files are skipped, and so are paths the user excludes. | `app/ingest/` |
| Preprocess | Language detection, error-tolerant tree-sitter parsing (broken code still gets reviewed), and chunking at function and class boundaries: small units packed to about 250 lines, never more than 500, each with its imports and enclosing signatures and real line numbers. | `app/preprocess/`, `app/languages/` |
| Static analysis | Analyzers run in parallel as subprocesses with a minimal environment, isolated configuration and a timeout; a missing or failing tool is reported and skipped. Output is normalized into one `Finding` schema and duplicates across tools are merged. | [static-analysis.md](static-analysis.md) |
| Review | Each chunk goes to a model with its static findings and metrics. The model judges each static finding (confirmed, false positive, needs context) and reports new issues, each with lines, evidence, rationale and confidence. Answers that cite lines or code that do not exist are discarded. | [review.md](review.md) |
| Verify | A model from another provider re-checks serious AI findings. A rejected finding is marked for human review, not deleted. | [review.md](review.md#cross-model-verification) |
| Report | Quality score (0 to 100, with its formula), executive summary, findings, what was not counted and why, and which provider saw which file. HTML, JSON and SARIF 2.1.0. | [api.md](api.md) |

## 4. The LLM router

Every model call goes through one router (`app/llm/router.py`). Each task (review, style, verify,
summarize) has a preference list of providers. For each call the router:

1. skips providers the request excludes, hosted providers without consent, and providers whose circuit
   breaker is open (after failures, a 429, an exhausted quota or a bad key);
2. books rate-limit capacity: requests per minute and per day in sliding windows, tokens per minute in
   a bucket, all at 80 % of the provider's limit; if the wait would be too long it moves on;
3. calls the provider with a timeout, validates the answer, and on failure pauses the provider for as
   long as the failure suggests before trying the next one.

Every attempt, successful or not, becomes a `CallRecord`, which is how the report shows who saw what.
Identical requests are answered from a cache. Details in [routing.md](routing.md).

## 5. Data model

A **finding** has a location (file, lines, columns), a category (bug, security, style, performance,
maintainability, typing), a severity, a title, message, rationale, evidence and suggested change, a
CWE id where it applies, a confidence, and its **provenance**: `sources` (the analyzers and models that
reported or confirmed it), `verified_by`, and an `ai_note` when a model's judgement changed it.

A finding's **status** is `open`, `accepted`, `rejected` (both set by the reviewer), `dismissed_by_ai`
or `needs_review` (set by review and verification). AI-only findings below a confidence threshold (0.6)
are kept but not reported by default. A model may never dismiss a high or critical security finding
from static analysis on its own.

## 6. Security and privacy

| Threat | Defence |
|---|---|
| Malicious archives (zip slip, bombs, symlinks) | One extraction path with path, size, count and ratio checks, tested against attack archives |
| An upload's config switching analyzers off (`ruff.toml`, `.bandit`, `.ignore`, plugins) | Isolated tool configuration; each defence has a test that fails without it ([static-analysis.md §3](static-analysis.md)) |
| Uploaded code executing | Nothing is imported or run; tools parse. Python tools run with `python -I` so uploaded modules cannot shadow them |
| Secrets reaching a model or a report | Lines and values flagged by detect-secrets are masked before any prompt is built and in all evidence |
| Prompt injection in code or comments | The prompt declares code and findings to be data; every AI finding must be grounded in real lines and quoted code; models cannot dismiss serious static security findings |
| Code leaving the machine without consent | Hosted providers need explicit consent per scan; without it only a local model or static analysis runs |
| Leaked or guessed scan ids | Unguessable ids; unknown and malformed ids are indistinguishable; results expire with the upload |

## 7. Key decisions

| Decision | Instead of | Why |
|---|---|---|
| Static analysis first, models second | LLM-only review | The evaluation shows each finds what the other misses; static context also lets models judge rule findings |
| A custom router of about 300 lines | LiteLLM | Small, fully tested with fake providers and a fake clock, and no large dependency (its PyPI releases were compromised in 2026) |
| Sliding windows for request limits | Token buckets | A bucket that starts full allows twice its limit in the first minute; the evaluation caught this against Gemini's free tier |
| Direct HTTP clients (`httpx`) | Provider SDKs | One timeout and retry policy (the router's), exact error mapping, recorded-response tests |
| JSON files per scan | A database | Lookups are by scan id and results must expire with the code; nothing to migrate |
| Prism for the code view | Monaco | Read-only view; Monaco is megabytes of JavaScript loaded from a CDN by default |
| Reviewer decisions change counts and score | Read-only reports | The reviewer, not the model, has the last word |

## 8. Extending

- **A language:** add an adapter in `app/languages/` (detection, parser, chunk boundaries) and register
  it; generic analyzers (Lizard, detect-secrets, Opengrep) and LLM review apply automatically.
- **An analyzer:** implement the `Analyzer` protocol in `app/static/analyzers/`, normalize its output to
  `Finding`, and add a test that it cannot be disabled by the upload's configuration.
- **A provider:** implement `LLMProvider` (or reuse the OpenAI-compatible client), add its limits and
  routing to `backend/config/providers.yaml`, and its key and model id to `.env`.

See also: [tech stack](tech-stack.md), [coding rules](coding-rules.md), [web UI](ui.md),
[model selection](model_selection.md), [evaluation](evaluation.md).
