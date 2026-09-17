# Margin — AI Code Review Assistant

> Static analyzers find it. Three LLMs check it. You decide what changes.

Margin reviews a single source file or a zipped project in two passes.

1. **Static analysis.** Deterministic analyzers (Ruff, Bandit, mypy, Radon, Vulture, Lizard, detect-secrets, Opengrep) find concrete bugs, security issues, style deviations and complexity hotspots.
2. **LLM review.** Three hosted LLMs (Google Gemini, Meta Llama via Hugging Face, and an open model on NVIDIA NIM) take the static findings as structured context. They confirm or dismiss each finding, add semantic issues the analyzers can't see, and back every point with a rationale and the exact evidence from the code.

A router that knows each provider's rate limits sends every task to the best-suited model and falls back cleanly when a quota runs out. A verifier checks evidence and runs a second model on serious findings, so false positives are filtered out before you see them.

> **Status:** in active development. Safe upload handling, structure-aware chunking, the static analysis engine with its CLI, and the rate-limit-aware LLM router work today; LLM review, the web API and the web UI are being added module by module.

## Planned features

- **Bugs and security:** common bug patterns and vulnerabilities, tagged with CWE ids.
- **Style:** deviations from established guides (PEP 8 / PEP 257 for Python).
- **Optimization:** performance and maintainability suggestions driven by complexity metrics.
- **Hybrid, grounded review:** static findings are passed to the LLMs as structured input, and every LLM finding must cite real lines and quote real code.
- **Rate-limit-aware routing:** token buckets, circuit breakers, role-based provider assignment, fallbacks and a response cache.
- **Interactive and batch modes:** a web UI with live scan progress, a CLI, and SARIF output for CI/CD.
- **Privacy:** explicit consent before any code leaves the machine, secret redaction before every LLM call, and automatic deletion of uploads.
- **Evaluation:** precision/recall/F1, style accuracy, latency and robustness on a labeled dataset.

## Architecture at a glance

```
upload (file / .zip)
  → ingest        safe unzip, filtering
  → preprocess    language detection, tree-sitter parsing, chunking (≤ 500 lines)
  → static        analyzers in parallel, normalized into one Finding schema
  → context       code + findings + metrics per chunk, secrets redacted
  → LLM review    router → Gemini / Llama (HF) / NVIDIA NIM
  → verify        line + evidence checks, dedupe, cross-model verification
  → report        quality score, HTML / JSON / SARIF
```

## Repository layout

```
backend/            FastAPI service, analysis pipeline, CLI
  app/              application package
  scripts/          developer utilities (e.g. model discovery)
  tests/            pytest suite
frontend/           React + TypeScript web interface
docs/               design and engineering documentation
.github/workflows/  continuous integration
```

## Development setup

### Prerequisites

| Tool | Version |
|---|---|
| [Python](https://www.python.org/downloads/) | 3.11 or newer (3.12 recommended) |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | recent release |
| [Node.js](https://nodejs.org/) | 22.12 or newer (24 LTS recommended) |
| Git | any recent version |

### Backend

```bash
cd backend
cp .env.example .env    # optional for now: the service starts without API keys
uv sync
uv run uvicorn app.main:create_app --factory --reload
```

The API runs at http://127.0.0.1:8000, with interactive docs at http://127.0.0.1:8000/docs.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Requests to `/api` are proxied to the backend.

### LLM providers

Margin uses Google Gemini, Hugging Face Inference Providers and NVIDIA NIM, and optionally a local model served by [Ollama](https://ollama.com). Add the keys to `backend/.env` (links to create each key are in `.env.example`), then list the model ids your keys and local server can use:

```bash
cd backend
uv run python scripts/list_models.py
```

Put the chosen ids in `.env` (`GEMINI_MODEL`, `HF_MODEL_LARGE`, `HF_MODEL_SMALL`, `NVIDIA_MODEL`, `LOCAL_MODEL`). A provider without its key or model id is simply not used. No keys at all? `LLM_MODE=mock` runs everything offline with canned answers. Rate limits and task routing are in `backend/config/providers.yaml`; see [LLM routing](docs/routing.md).

### Scanning from the command line

```bash
cd backend
uv run margin scan path/to/project            # table of findings
uv run margin scan project.zip --format json --output report.json
uv run margin scan src --fail-on high          # exit code 1 if any high or critical finding
```

The CLI runs Ruff, Bandit, mypy, Radon, Vulture, Lizard and detect-secrets, plus Opengrep when its binary is
installed ([releases](https://github.com/opengrep/opengrep/releases); set `OPENGREP_PATH` if it is not on `PATH`).
Exit codes: `0` success, `1` a finding reached `--fail-on`, `2` the input was rejected.

### Quality checks

These are the same checks CI runs on every pull request.

```bash
# backend
cd backend
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest --cov

# frontend
cd frontend
npm run format:check && npm run lint && npm run typecheck && npm test && npm run build
```

Install the pre-commit hooks once so formatting, linting and secret scanning run before every commit:

```bash
cd backend
uv run pre-commit install
```

## Documentation

- [Coding rules](docs/coding-rules.md)
- [Tech stack](docs/tech-stack.md)
- [Static analysis engine](docs/static-analysis.md): analyzers, finding normalization, and how untrusted code is analyzed safely
- [LLM routing](docs/routing.md): providers, task routing, rate limits, circuit breakers, caching and the consent gate

## License

[MIT](LICENSE)
