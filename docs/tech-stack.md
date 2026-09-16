# Tech Stack

This document records which technologies Margin uses and why. Exact versions are pinned in `backend/uv.lock` and `frontend/package-lock.json`. Every report also records the analyzer and model versions it ran with.

## 1. Overview

```
┌──────────────────────┐   REST + SSE    ┌──────────────────────────────────────────┐
│ Web UI               │ ──────────────► │ FastAPI backend                          │
│ React · TypeScript   │                 │  ingest → preprocess → static analysis   │
│ Tailwind · Monaco    │ ◄────────────── │  → context → LLM router → verify → report │
└──────────────────────┘  live events    └───────────┬──────────────────┬───────────┘
                                                     │                  │
┌──────────────────────┐   same pipeline             │ subprocesses     │ HTTPS (with consent)
│ CLI (Typer)          │ ─────────────────►          ▼                  ▼
│ GitHub Action (SARIF)│              Ruff · Bandit · mypy ·   Gemini · Llama (HF) · NVIDIA NIM
└──────────────────────┘              Radon · Vulture · Lizard ·
                                      detect-secrets · Opengrep
```

The web UI, the CLI and the GitHub Action all call the same pipeline, so interactive and batch modes behave the same way.

## 2. Backend

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 (supports ≥ 3.11) | The analysis ecosystem (Ruff, Bandit, mypy, Radon, tree-sitter bindings) and every LLM SDK are Python-first. |
| Package management | uv | Fast, reproducible installs from a committed lock file. |
| Web framework | FastAPI + Uvicorn | Async-native, Pydantic validation at the edge, automatic OpenAPI schema (used to generate frontend types). |
| Live progress | Server-Sent Events | The stream is one-way (server → browser). SSE is simpler than WebSockets, works through proxies and reconnects with `Last-Event-ID`. |
| Data models | Pydantic v2 | One schema for API bodies, analyzer output, LLM I/O and events. |
| Configuration | pydantic-settings | Typed settings from environment variables and `.env`. API keys never reach the frontend. |
| Persistence | SQLModel on SQLite | Scans, findings, LLM call logs and the response cache in a single file, with zero setup. Enough for a single-node prototype. |
| CLI | Typer + Rich | Batch mode (`margin scan ./project --format sarif`) on the same pipeline. |
| Logging | structlog (JSON) | Structured, filterable logs with scan and stage context. |
| Templates | Jinja2 | HTML reports and prompt rendering. |
| HTTP | httpx | Async client with timeouts, mocked in tests with respx. |

## 3. LLM providers

The brief asks for open-source or publicly available models. Margin uses three hosted providers **together**: each task type goes to the provider best suited to it, and the others serve as fallbacks.

| Provider | Access | Models | Primary role | Why |
|---|---|---|---|---|
| NVIDIA NIM | OpenAI-compatible API (`integrate.api.nvidia.com`) | An open-weight instruct / coder model from the NVIDIA API catalog | Bulk chunk review (bugs, security, performance) | The most generous free rate limit, so it carries the highest-volume task. |
| Hugging Face Inference Providers | OpenAI-compatible router (`router.huggingface.co`) | Meta Llama 3.3 70B Instruct, Llama 3.1 8B Instruct | Style review (8B); fallback review (70B) | Open-weight Llama models. The small model is cheap enough for high-volume style checks. |
| Google Gemini | `google-genai` SDK | Gemini Flash (free tier) | Cross-model verification, project summary | Long context and strong code reasoning. Publicly available, but a closed model, so it is used behind the consent gate. |
| Mock | In-process | Canned JSON fixtures | Tests and CI | Deterministic, free and needs no keys. |

Model ids are not hard-coded. `scripts/list_models.py` lists the models each key can access, and the chosen ids go in `.env`.

### Privacy

- Code is sent to external providers only after explicit consent, and each provider can be switched off.
- Secrets detected in the code are replaced with placeholders before any request.
- Only the chunk under review is sent, never the whole repository.
- Uploaded code is deleted after a retention window.

## 4. Routing

A custom asyncio router, about 300 lines, sits between the pipeline and the providers:

| Mechanism | Purpose |
|---|---|
| Role-based preference lists | Each task (`review`, `style`, `verify`, `summarize`) has an ordered list of providers. |
| Token buckets (RPM / TPM / RPD) | Stay below each provider's limits, with a 20 % safety margin. |
| Concurrency semaphores | Prevent bursts that trigger rate limiting. |
| Circuit breakers | Stop calling a provider after 429s, quota errors or repeated failures, and probe again later. |
| Fallbacks | Route to the next provider when one is unavailable; `verify` always excludes the provider that produced the finding. |
| Response cache | Re-scanning unchanged code costs no API calls. |
| Budget planner | Estimates calls before a scan and degrades gracefully when quotas are tight. |

**Alternative considered:** LiteLLM provides similar routing out of the box. A custom router was chosen for three reasons: it stays small, it can be fully unit-tested with fake providers and a fake clock, and it avoids a large dependency whose PyPI releases were compromised in a 2026 supply-chain incident.

Provider limits live in `backend/config/providers.yaml`, so they can be updated without code changes.

## 5. Static analysis toolchain

| Tool | Finds | Languages |
|---|---|---|
| tree-sitter (`tree-sitter-language-pack`) | Syntax trees, function boundaries, broken or incomplete regions | 100+ |
| Ruff | PEP 8 style, pyflakes and bugbear bugs, simplifications, performance anti-patterns, docstrings | Python |
| Bandit | Security issues with CWE ids | Python |
| mypy | Type errors | Python |
| Radon | Cyclomatic complexity, maintainability index | Python |
| Vulture | Dead code | Python |
| Lizard | Complexity, function length, parameter count | ~20 languages |
| detect-secrets | Hard-coded credentials (also drives redaction) | Any text |
| Opengrep | Pattern and taint rules, using the project's own rules in `backend/rules/` | 30+ |

- **Language support.** Python gets full support. Other languages get basic support: tree-sitter chunking, Lizard, detect-secrets, Opengrep and LLM review. Adding a language means writing one adapter in `backend/app/languages/`.
- **Normalization.** All output is normalized into one `Finding` schema (file, lines, category, severity, rule id, CWE, sources, confidence).
- **Optional tools.** A tool that is not installed is reported as *skipped* and the scan continues.

## 6. Frontend

| Concern | Choice | Why |
|---|---|---|
| Build | Vite + React 19 + TypeScript | Fast development server, a standard modern stack, strict typing. |
| Styling | Tailwind CSS v4 + shadcn/ui | Design tokens in CSS, accessible Radix-based components that live in the repo. |
| Code view | Monaco editor (`@monaco-editor/react`) | Real editor rendering with gutter decorations for findings. Lazy-loaded so the landing page stays fast. |
| Server state | TanStack Query | Caching, loading and error states for REST calls. |
| Live scan state | Zustand + native `EventSource` | A small store fed by the SSE stream. |
| Routing | React Router | Landing, scan and results pages. |
| Upload | react-dropzone | Accessible drag-and-drop file input. |
| Icons, toasts | lucide-react, sonner | Lightweight and consistent. |
| Fonts | Bricolage Grotesque, IBM Plex Sans / Mono (self-hosted via Fontsource) | No runtime calls to third-party font CDNs. |
| API types | openapi-typescript | Types generated from the backend schema, so frontend and backend cannot drift. |

## 7. Quality and delivery

| Concern | Choice |
|---|---|
| Backend tests | pytest, pytest-asyncio, pytest-cov, respx (HTTP mocking), jsonschema (SARIF validation) |
| Frontend tests | Vitest, Testing Library |
| Lint and types | Ruff, mypy (strict), ESLint, Prettier, `tsc` |
| Pre-commit hooks | Ruff, ruff-format, detect-secrets, whitespace and end-of-file fixers |
| CI | GitHub Actions: lint, type check, tests, `pip-audit` and `npm audit` |
| CI/CD integration | A GitHub Action that runs `margin scan` and uploads SARIF to GitHub code scanning |
| Reports | HTML (Jinja2), JSON, SARIF 2.1.0 |
| Demo | Google Colab notebook, with API keys read from Colab Secrets |

## 8. Platform notes

- **Line endings** are normalized to LF (`.gitattributes`), so generated diffs match on Windows and Linux.
- **PDF export** is deferred. WeasyPrint needs GTK libraries that are awkward to install on Windows, and the HTML report prints cleanly to PDF from a browser.
- **Opengrep** is a standalone binary. It is installed in CI and optional on developer machines.
