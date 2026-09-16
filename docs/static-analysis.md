# Static Analysis Engine

The static engine runs eight open-source analyzers over an uploaded project and turns their output into one finding format. Its results are the structured input for LLM review, and they stand on their own in the CLI.

Code: `backend/app/static/`. Entry point: `run_static_analysis` in `runner.py`.

## 1. Analyzers

| Analyzer | Finds | Languages | Category and default severity |
|---|---|---|---|
| **Ruff** | PEP 8 style, pyflakes and bugbear bugs, simplifications, performance anti-patterns | Python | style low/info; bug medium (undefined names high); unused code maintainability low |
| **Bandit** | Security issues with CWE ids | Python | security; severity combines Bandit severity and confidence |
| **mypy** | Type errors | Python | typing medium |
| **Radon** | Cyclomatic complexity (rank D or worse), maintainability index below 20, line counts | Python | maintainability low (D) / medium (E, F, low MI) |
| **Vulture** | Unused and unreachable code (confidence ≥ 80 %) | Python | maintainability low |
| **Lizard** | Function length > 80 lines, more than 6 parameters, complexity > 15; per-function metrics | Python, JavaScript, TypeScript, Java, Go | maintainability low |
| **detect-secrets** | Hardcoded credentials | Any text file | security high, CWE-798 |
| **Opengrep** | Margin's own security rules (section 5) | Python, JavaScript, TypeScript | security; ERROR → high, WARNING → medium |

A tool that is not installed is reported as *skipped*. Opengrep is a standalone binary and optional on developer machines; CI installs a checksum-verified copy.

## 2. From tool output to findings

1. **Run in parallel.** Every applicable analyzer runs concurrently under a timeout (120 s by default). A tool that fails, times out, crashes or is missing becomes a `ToolRun` record, and the scan continues with the others.
2. **Normalize.** Each analyzer maps its native output onto `Finding` (`app/findings.py`):
   - paths relative to the upload root, POSIX style
   - 1-based inclusive lines
   - category and severity
   - rule id, sources, confidence and CWE
3. **Merge duplicates.** Several tools report the same issue. Equivalent findings on the same line are merged into one finding. It is led by the most severe report and keeps every source (`dedupe.py`), for example:
   - Ruff F401 and Vulture's unused import
   - Bandit B602 and the Opengrep shell-injection rule
   - Bandit B105 and detect-secrets

   Findings from the same tool are never merged with each other.
4. **Attach evidence.** Up to five offending lines are copied into the finding (`evidence.py`). Findings about secrets carry a redaction marker instead, and their messages never quote the secret.
5. **Order and emit.** Findings are sorted most severe first and sent as events to the CLI or the web UI.

File metrics from Radon (size, maintainability index) and Lizard (per-function complexity, length and parameters) are merged per file for the quality score.

## 3. Running analyzers safely on untrusted code

Uploaded code is only ever read. Analyzers, however, are general-purpose tools that read configuration from the project they scan, and some configuration executes code. Every measure below was reproduced as an attack before it was fixed, and each has a regression test that fails if the measure is removed.

| Risk | Reproduced attack | Measure |
|---|---|---|
| mypy plugins run arbitrary code | A `mypy.ini` in the upload loaded a plugin that wrote a file during the scan | Run from an empty scratch directory **and** pass `--config-file=`; two independent tests |
| Python module shadowing | An uploaded `detect_secrets.py` ran instead of the real module, because `python -m` puts the working directory first on `sys.path` | Every Python tool runs as `python -I` (isolated mode) |
| Ruff configuration hides findings | An uploaded `ruff.toml` with `extend-exclude`, `include` or `per-file-ignores` removed every finding | `ruff check --isolated` |
| Bandit configuration disables checks | An uploaded `.bandit` with `tests = B101` made Bandit produce no report at all | `--ini` points at Margin's own empty file |
| Suppression comments hide issues | `# nosec` hid a `shell=True` finding | `bandit --ignore-nosec` |
| Opengrep ignore files hide targets | An uploaded `.semgrepignore` hid every file, even with `--no-git-ignore` | Opengrep runs from the scratch directory |
| Radon and Vulture configuration | `setup.cfg`, `radon.cfg` and `[tool.vulture]` are read from the working directory | Both run from the scratch directory |
| Secrets leaking into reports | Bandit quotes hardcoded passwords in its message | Messages rewritten, evidence redacted |
| Backend credentials reaching tools | — | Tools get a minimal environment built from scratch; no API keys are passed on |

Other properties of every tool process:
- Commands are argument lists, never shell strings.
- Home and temp directories point at the per-scan scratch directory.
- Cancelling a scan kills the process.

## 4. Robustness

- **mypy.** A single file with a syntax error stops mypy for the whole project. Files are therefore pre-checked with `ast.parse` (parsing never executes code), and only parseable files are type-checked; Ruff still reports the syntax errors.
- **Duplicate module names.** Uploads often contain several `utils.py` files. `MYPYPATH` plus `--explicit-package-bases` keeps them distinct.
- **Large projects.** File lists go through argument files or directory arguments, so projects of any size stay within command-line limits.
- **Windows.** Opengrep needs `AppData\Local` inside the redirected profile directory; the analyzer creates it.

## 5. Custom Opengrep rules

The rules live in `backend/app/static/rules/*.yaml` and were written for this project, so no third-party rule-pack license applies. Each rule records `cwe`, `category` and `confidence`, and a test enforces that.

| Rule | CWE |
|---|---|
| `python-shell-command-from-dynamic-input` | CWE-78 |
| `python-sql-built-with-string-formatting` | CWE-89 |
| `python-yaml-load-without-safe-loader` | CWE-502 |
| `python-tls-certificate-verification-disabled` | CWE-295 |
| `python-web-debug-mode-enabled` | CWE-489 |
| `python-password-hashed-with-fast-hash` | CWE-916 |
| `python-insecure-random-for-secret` | CWE-330 |
| `python-jwt-signature-not-verified` | CWE-347 |
| `python-insecure-temporary-file` | CWE-377 |
| `python-eval-of-dynamic-value` | CWE-95 |
| `javascript-shell-command-from-dynamic-input` | CWE-78 |
| `javascript-eval-of-dynamic-value` | CWE-95 |
| `javascript-html-injection-via-inner-html` | CWE-79 |

On the seeded sample in `tests/static/test_opengrep.py`, every rule fires on its vulnerable variant, and the safe variants produce no findings: parameterized SQL, `SafeLoader`, argument lists, static `innerHTML` and literal `eval`.

## 6. Extending the engine

- **Add a rule:** add an entry to a YAML file in `app/static/rules/` with `cwe`, `category` and `confidence` metadata, plus a vulnerable and a safe sample in the Opengrep tests. If Bandit reports the same issue, add both to `EQUIVALENT_RULES` in `dedupe.py`.
- **Add an analyzer:** write a module in `app/static/analyzers/` that implements the `Analyzer` protocol (`name`, `applies_to`, `analyze`). Run the tool through `run_tool`, then add it to `default_analyzers`. Before relying on it, check whether the tool reads project configuration or executes project code, and add a test that plants hostile configuration.

## 7. Limitations

- Projects are analyzed without their dependencies installed. mypy therefore ignores missing imports, and some type errors across package boundaries go unnoticed.
- mypy skips following imports, so type information from other modules in the project is not used.
- Keyword and entropy detectors in detect-secrets also match test fixtures; their findings get lower confidence.
- Language support beyond Python is basic: complexity metrics, secrets and a few security rules.
