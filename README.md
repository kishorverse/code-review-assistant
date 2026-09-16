# Margin — AI Code Review Assistant

> Static analyzers find it. Three LLMs check it. You decide what changes.

Margin reviews a single source file or a zipped project in two passes.

1. **Static analysis.** Deterministic analyzers (Ruff, Bandit, mypy, Radon, Vulture, Lizard, detect-secrets, Opengrep) find concrete bugs, security issues, style deviations and complexity hotspots.
2. **LLM review.** Three hosted LLMs (Google Gemini, Meta Llama via Hugging Face, and an open model on NVIDIA NIM) take the static findings as structured context. They confirm or dismiss each finding, add semantic issues the analyzers can't see, and back every point with a rationale and the exact evidence from the code.

A router that knows each provider's rate limits sends every task to the best-suited model and falls back cleanly when a quota runs out. A verifier checks evidence and runs a second model on serious findings, so false positives are filtered out before you see them.

> **Status:** in active development. Setup and usage instructions are added as each module lands.

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
backend/     FastAPI service, analysis pipeline, CLI
frontend/    React web interface
eval/        datasets, evaluation and benchmark scripts
notebooks/   Colab demo
docs/        design and engineering documentation
scripts/     developer utilities
```

## Documentation

- [Coding rules](docs/coding-rules.md)
- [Tech stack](docs/tech-stack.md)

## License

[MIT](LICENSE)
