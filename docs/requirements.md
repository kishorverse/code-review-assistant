# Requirements Coverage

How each item of the project brief is met, and where to see it. ✅ done, ◐ partly, ✗ not done.

## Technical objectives

| Requirement | Status | Where |
|---|---|---|
| Integrate LLMs with static code analysis | ✅ | Pipeline: [design](design.md); static findings go to the models as structured context: [LLM review](review.md) |
| Detect common bug patterns and security vulnerabilities | ✅ | Ruff, Bandit, mypy, Opengrep with custom rules, detect-secrets, plus LLM review; CWE ids; [evaluation](evaluation.md) §2 |
| Identify style deviations and suggest improvements | ✅ | Ruff (PEP 8, at the project's declared line length) and an LLM style task; [evaluation](evaluation.md) §3 |
| Recommend optimizations for performance or readability | ✅ | Performance category (LLM and Ruff PERF), complexity metrics (Radon, Lizard), suggested changes on each finding |
| Multiple languages, or one with extensibility | ✅ | Python in full; JavaScript, TypeScript, Java and Go through adapters in `backend/app/languages/` |
| Clear, concise, actionable feedback | ✅ | Every finding: title, message, rationale ("why it matters"), quoted evidence, suggested change |

## System architecture

| Requirement | Status | Where |
|---|---|---|
| Preprocessing module that parses and tokenizes | ✅ | `app/preprocess/`: language detection, tree-sitter parsing, chunking at function and class boundaries |
| Static analysis engine for syntactic and semantic features | ✅ | `app/static/`: [static analysis](static-analysis.md) |
| LLM inference module that interprets features and writes feedback | ✅ | `app/review/`, `app/llm/`: [LLM review](review.md), [routing](routing.md) |
| Batch and interactive modes | ✅ | CLI and GitHub Action (batch); web UI with live progress and the web API (interactive) |
| IDE or CI/CD integration | ◐ | CI/CD: SARIF to GitHub code scanning, `--fail-on` exit codes. IDE: no plugin; the API and SARIF are what one would use |
| Language components decoupled; LLMs and rules easy to update | ✅ | Language adapters; providers and routing in `config/providers.yaml`; model ids in `.env`; versioned prompts; Opengrep rules as YAML |

## Deliverables

| Requirement | Status | Where |
|---|---|---|
| Functional prototype that analyzes code and writes review comments | ✅ | Web UI, CLI, API; [README](../README.md) quick start |
| Documentation: system design, model selection, integration approach | ✅ | [design](design.md), [model selection](model_selection.md), [routing](routing.md), [web API](api.md), [tech stack](tech-stack.md) |
| Test suite demonstrating detection of bugs, style issues and optimizations | ✅ | 750+ backend and 18 frontend tests in CI; the labeled dataset in `eval/datasets/seeded/` with per-label results |
| Report on model performance and limitations, with recommendations | ✅ | [evaluation](evaluation.md): results, limitations (§8), recommendations (§9) |

## Modeling requirements

| Requirement | Status | Where |
|---|---|---|
| Prompt-engineer LLMs for code | ✅ | Versioned prompts in `app/llm/prompts/` with worked examples, including one where the right answer is "no issue" |
| Static analysis outputs as structured input to the LLM | ✅ | Static findings as JSON with short ids, judged one by one: [LLM review](review.md) |
| Handle ambiguous or incomplete code gracefully | ✅ | Error-tolerant parsing, syntax errors reported as bugs, partial regions still reviewed; a model call failing never fails a scan |
| Precise, relevant feedback that avoids false positives | ✅ | Grounding (lines and quoted code must exist), a confidence threshold, cross-model verification, protected serious static findings; precision 0.88 in the evaluation |
| Explanations or rationale behind each suggestion | ✅ | `rationale` on every AI finding, shown as "Why it matters" |

## Evaluation metrics

| Requirement | Status | Where |
|---|---|---|
| Precision, recall and F1 for bugs and vulnerabilities | ✅ | [evaluation](evaluation.md) §2, per category and per CWE |
| Accuracy on style violations against established guides | ✅ | [evaluation](evaluation.md) §3 (PEP 8 / PEP 257 labels) |
| Usefulness of suggestions rated by expert reviewers | ◐ | Blind rating sheet, kappa scripts and instructions are ready (`eval/human_eval/`); the ratings are not collected yet |
| Latency and throughput | ✅ | [evaluation](evaluation.md) §5 |
| Robustness across codebases and languages | ◐ | Failures, outages and broken code in §6; static scans of Python and TypeScript codebases and an LLM review of a TypeScript file. No public benchmark datasets or third-party repositories yet |

## Implementation constraints

| Requirement | Status | Where |
|---|---|---|
| Open-source or publicly available LLMs and tools | ✅ | Open-weight gpt-oss, Nemotron, Qwen; publicly available Gemini; all analyzers open source: [licenses](licenses.md) |
| Code snippets up to about 500 lines | ✅ | Chunks never exceed 500 lines; the latency benchmark includes 500-line files |
| Privacy: no code to external services unless permitted | ✅ | Consent per scan (`--allow-external` / consent box), secrets masked first, provenance of every call, uploads deleted after 24 hours |
| Computational efficiency, near-real-time feedback | ◐ | Static review in seconds; LLM review takes minutes on free tiers (§5); a fast paid provider is the recommended fix |
| Document third-party dependencies and license compliance | ✅ | [licenses](licenses.md) |

## Stretch goals

| Goal | Status | Where |
|---|---|---|
| Multiple languages, language-agnostic analysis | ◐ | Five languages; generic analyzers (Lizard, detect-secrets, Opengrep) and LLM review for all |
| Learning from user feedback | ✗ | Reviewer decisions are stored per scan; using them is future work |
| Interactive interface or IDE plugin | ◐ | Interactive web UI; no IDE plugin |
| Automated refactoring suggestions with safe previews | ◐ | Suggested changes as text; no diff preview or automatic application |
| Security-specific analysis for advanced vulnerabilities | ✅ | Bandit, custom Opengrep rules (CWE-tagged), detect-secrets, LLM security review with CWE ids |

## Submission

| Requirement | Status | Where |
|---|---|---|
| Public GitHub repository, well named | ✅ | github.com/kishorverse/code-review-assistant |
| README: title, description, setup, usage, dependencies, approach | ✅ | [README](../README.md) |
| Regular, logical commits with clear messages | ✅ | One branch and pull request per module; see the commit history |
| `.gitignore`, no unnecessary files | ✅ | `.gitignore`; generated and secret files excluded |
| Colab notebook | ✅ | `notebooks/margin_demo.ipynb`, with an "Open in Colab" badge in the README |
| Unlisted YouTube video | ✗ | To record and upload |
