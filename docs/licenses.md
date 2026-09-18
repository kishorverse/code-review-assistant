# Licenses

Margin itself is released under the [MIT license](../LICENSE). This page lists what it depends on and
under which terms, as declared by each package's own metadata (versions from `backend/uv.lock` and
`frontend/package-lock.json` at the time of writing). The custom Opengrep rules in
`backend/app/static/rules/` were written for this project, so no third-party rule-pack license applies.

## Analyzers

Each runs as a separate process on the files being reviewed; none is modified.

| Tool | Version | License |
|---|---|---|
| Ruff | 0.16.8 | MIT |
| Bandit | 1.9.4 | Apache-2.0 |
| mypy | 2.3.1 | MIT |
| Radon | 6.0.1 | MIT |
| Vulture | 2.16 | MIT |
| Lizard | 1.24.0 | MIT |
| detect-secrets | 1.5.0 | Apache-2.0 |
| Opengrep | 1.30.0 | LGPL-2.1; installed as a separate binary, not linked or redistributed |
| tree-sitter and the Python, JavaScript, TypeScript, Java and Go grammars | 0.23–0.25 | MIT |

## Backend

| Package | License |
|---|---|
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| Pydantic, pydantic-settings | MIT |
| httpx | BSD-3-Clause |
| structlog | MIT or Apache-2.0 |
| Typer, Rich | MIT |
| Jinja2 | BSD-3-Clause |
| PyYAML | MIT |
| python-multipart | Apache-2.0 |
| Development: pytest, pytest-cov, jsonschema, pre-commit | MIT |
| Development: pytest-asyncio | Apache-2.0 |
| Development: respx | BSD-3-Clause |

## Frontend

| Package | License |
|---|---|
| React, React DOM, React Router, TanStack Query, Zustand | MIT |
| Tailwind CSS, shadcn/ui, Radix UI, `cn`, tw-animate-css | MIT |
| class-variance-authority | Apache-2.0 |
| Prism | MIT |
| react-dropzone, sonner | MIT |
| Lucide icons | ISC |
| Fonts: Bricolage Grotesque, IBM Plex Sans, IBM Plex Mono (via Fontsource) | SIL Open Font License 1.1 |
| Development: Vite, Vitest, ESLint, Prettier, Testing Library, jsdom | MIT |
| Development: TypeScript | Apache-2.0 |

## Models and APIs

Models are called over their providers' APIs; no weights are distributed with Margin. Each provider's
terms of service apply to what is sent to it. Check them before reviewing code you may not share:
some free tiers allow the provider to use submitted content to improve its services.

| Model (as configured) | Provider | Terms |
|---|---|---|
| Gemini 3.5 Flash | Google AI Studio (Gemini API) | Proprietary model; Gemini API terms of service |
| Nemotron 3 Super 120B-A12B | NVIDIA NIM (build.nvidia.com) | NVIDIA open model license; NVIDIA API trial terms |
| gpt-oss-120b | Hugging Face Inference Providers | Apache-2.0 weights; Hugging Face and the serving provider's terms |
| Qwen3-Coder-30B-A3B-Instruct | Hugging Face Inference Providers | Apache-2.0 weights; Hugging Face and the serving provider's terms |
| Qwen3-VL 4B Instruct | Local, through Ollama | Apache-2.0 weights; nothing leaves the machine |

Model ids are configuration (`backend/.env`), so the models in use may differ from this table.

## Evaluation data

The seeded dataset in `eval/datasets/seeded/` was written for this project and is covered by the MIT
license with the rest of the repository.
