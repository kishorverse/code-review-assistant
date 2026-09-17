# Coding Rules

These rules keep the codebase consistent, reviewable and safe. They apply to every change. CI enforces everything that can be automated; the rest is checked in review.

## 1. Principles

1. **Readable over clever.** Prefer explicit names and straightforward control flow.
2. **Small units.** A function does one thing (aim for ≤ 40 lines). A module has one responsibility (aim for ≤ 400 lines). Split when either grows past that.
3. **Degrade, don't crash.** A failing analyzer, LLM provider or file must not fail the whole scan. Record the failure, emit an event and continue.
4. **All input is untrusted.** Uploaded archives, file contents, analyzer output and LLM responses are validated at the boundary before use.
5. **Deterministic tests.** No test depends on the network, the wall clock or API keys.

## 2. Architecture boundaries

| Concern | Lives in | Rule |
|---|---|---|
| Language-specific logic | `backend/app/languages/` | Other modules use the `LanguageAdapter` protocol. No `if language == "python"` anywhere else. |
| LLM access | `backend/app/llm/providers/` | Everything goes through the `LLMProvider` protocol and the router. No provider SDK imports outside `providers/`. |
| Prompts | `backend/app/llm/prompts/*.md` | Versioned files with a `PROMPT_VERSION` header. No prompt text in Python strings. |
| Custom analysis rules | `backend/app/static/rules/*.yaml` | Opengrep rules, each with `cwe`, `category` and `confidence` metadata. |
| Configuration | `backend/app/config.py` | `pydantic-settings`, loaded from the environment / `.env`. No `os.environ` access elsewhere. |
| Data crossing a boundary | Pydantic models | API bodies, LLM requests and responses, analyzer output, scan events. |

Dependencies such as providers, the clock, analyzers and the storage root are passed in rather than imported as globals, so tests can substitute fakes.

## 3. Security and privacy

- **Never execute, import or evaluate uploaded code.** Analyzers only read files.
- **Subprocesses** use `asyncio.create_subprocess_exec` with an argument list, never `shell=True`. Each one has a timeout, runs with `cwd` set to the scan directory, and gets a minimal environment without API keys.
- **Archives** are extracted only through `ingest/zipsafe.py`, which rejects absolute paths, `..` segments and symlinks, and enforces size, file-count and compression-ratio caps.
- **No code leaves the machine** unless the scan has `consent_external = true`. Secrets are redacted before every LLM call.
- **Logs** contain ids, paths, counts and timings. Never file contents, prompts that include code, or secrets.
- **Secrets are never committed.** `.env` is ignored, `.env.example` documents every variable with a placeholder, and `detect-secrets` runs as a pre-commit hook.
- **Every network call has an explicit timeout.**

## 4. Python (backend)

### Tooling

| Tool | Setting |
|---|---|
| Python | `>= 3.11` (developed on 3.12) |
| Package manager | `uv`, with `uv.lock` committed |
| Formatter | `ruff format` |
| Linter | `ruff check` with rule sets `E, W, F, I, B, UP, SIM, N, S, ASYNC, PERF, RUF`; line length 100 |
| Type checker | `mypy --strict` on `app/` and `scripts/`. Overrides only for untyped third-party packages, each with a comment explaining why. |
| Tests | `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` |

### Style

- Type hints on every function signature, including return types. Avoid `Any`; if it is unavoidable, contain it at the boundary.
- Naming: `snake_case` for functions, variables and modules; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants. No single-letter names outside comprehensions.
- `pathlib.Path` for all filesystem work. Paths stored in findings are POSIX-style and relative to the upload root.
- `Enum` or `Literal` instead of magic strings; named constants instead of magic numbers.
- Absolute imports (`from app.ingest.zipsafe import extract_archive`), sorted by Ruff. No wildcard imports.
- Google-style docstrings on public modules, classes and functions. Explain *why* and any non-obvious contract; don't restate the signature.
- Comments explain intent or constraints, not what the next line obviously does. No commented-out code.

### Async

- No blocking I/O inside `async def`. Use `asyncio.to_thread` for blocking work that must be called from async code.
- Bound concurrency with semaphores. Never fire an unbounded `asyncio.gather` at an external API.
- Every awaited external operation runs under a timeout (`asyncio.timeout`).

### Errors and logging

- Errors are defined in `app/errors.py` under a single `MarginError` base class. Raise specific subclasses.
- Catch the narrowest exception possible. No bare `except:`. `except Exception` is allowed only at top-level boundaries (a pipeline stage, an API handler) and must be logged.
- Log with `structlog` using key-value context (`scan_id`, `stage`, `tool`). No `print()` outside the CLI's user-facing output.

## 5. TypeScript (frontend)

### Tooling

| Tool | Setting |
|---|---|
| Build | Vite |
| Compiler | `strict: true`, `noUncheckedIndexedAccess: true` |
| Linter | ESLint with `typescript-eslint` and `eslint-plugin-react-hooks` |
| Formatter | Prettier |
| Tests | Vitest and Testing Library |

### Style

- No `any`: use `unknown` and narrow it. No non-null assertions (`!`) unless the invariant is explained in a comment.
- Function components and hooks only. One exported component per file.
- File names: `PascalCase.tsx` for components, `camelCase.ts` for hooks and utilities. Hooks start with `use`.
- API types are generated from the backend's OpenAPI schema, never hand-written copies.
- Server data goes through TanStack Query; the live scan stream goes through a Zustand store. Everything else stays in local component state.
- Styling uses Tailwind utilities and the theme tokens defined in `@theme`. No hard-coded colors in components.

### Accessibility

- Every interactive element is reachable by keyboard and has a visible focus ring.
- Severity is never shown by color alone: always an icon plus a text label.
- `prefers-reduced-motion` and `prefers-color-scheme` are respected.
- Form controls have labels. Live scan updates are announced through an ARIA live region.

## 6. Testing

- A feature lands together with its tests in the same pull request. A bug fix adds a regression test that fails without the fix.
- Unit tests never touch the network. LLM calls use the mock provider (`LLM_MODE=mock`), HTTP is faked with `respx`, and time-dependent code takes an injectable clock.
- Test names describe behavior, for example `test_rejects_entry_with_parent_traversal`.
- Analyzer normalizers are tested against recorded tool output stored in `tests/fixtures/`.
- Coverage target: at least 80 % for the backend core packages (ingest, preprocess, static, llm, verify, report).

## 7. Git workflow

### Branches

- `main` is always releasable: it builds and every check passes.
- Work happens on short-lived branches named `feat/<area>`, `fix/<area>`, `test/<area>`, `docs/<topic>` or `chore/<topic>`.
- A branch merges into `main` through a pull request with a merge commit, only after CI passes.

### Commits

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): summary

Optional body explaining why the change was made.
```

- **Types:** `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `chore`, `ci`, `build`.
- **Summary:** imperative mood, lower case, no trailing period, at most 72 characters.
- **Body:** explains *why*, wrapped at 72 characters. Optional for self-explanatory changes.
- **One logical change per commit.** Every commit builds and passes the tests.

Examples:

```
feat(ingest): reject zip entries with path traversal
test(ingest): add zip bomb and symlink cases
feat(llm): fall back to next provider on 429 with retry-after
```

### Pull requests

Every pull request description has three parts: **What** changed, **Why** it was needed, and **How it was tested** (commands run and cases covered).

### Never commit

Secrets or `.env` files, virtual environments, `node_modules/`, build output, databases, uploaded or extracted scan data, raw evaluation output, or editor and OS files. See [`.gitignore`](../.gitignore).

## 8. Definition of done

A pull request is ready to merge when:

- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run mypy` passes
- [ ] `uv run pytest --cov` passes and coverage has not dropped
- [ ] Frontend changes pass `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test` and `npm run build`
- [ ] Pre-commit hooks pass (`uv run pre-commit run --all-files` from `backend/`)
- [ ] New behavior is covered by tests, including error paths
- [ ] There are no secrets, debug output or dead code
- [ ] Documentation and the README reflect any user-visible change
- [ ] CI is green
