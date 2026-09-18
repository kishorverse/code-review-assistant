# Evaluation data and results

The evaluation harness is the `evaluation` package in `backend/`. This directory holds its data and
its output. The report is [docs/evaluation.md](../docs/evaluation.md).

```
eval/
  datasets/seeded/
    src/          32 Python modules written for this evaluation
    labels.json   the 55 issues injected into them
  results/
    runs/         every finding and model call, one JSON line per file and run
    scores.json   metrics per configuration
    tables.md     the tables quoted in docs/evaluation.md
    routing.md    router simulation
    latency.md    end-to-end timings
  human_eval/
    rating_sheet.csv   blind sample of AI suggestions to rate
    sample_key.json    which model wrote each sampled item (do not show raters)
```

## The seeded dataset

The modules are small, realistic pieces of services (repositories, billing, caches, clients), written
from scratch so no model can have seen them. Twenty-two contain injected issues; ten are clean controls,
several of which look risky but are safe (parameterized SQL, a checked path join, an argument-list
subprocess, constant-time token checks), so over-reporting shows up as false positives.

Each label in `labels.json` has a category (bug, security, performance, style, maintainability or
typing), a CWE for security issues, a severity, and `detection`: whether a static analyzer was
expected to find it (`static`) or it takes understanding the code (`semantic`). Labels were written
with the code, before any model saw it. A label names its line by an anchor, text found on exactly one
line, so editing a file cannot silently move a label: loading fails instead.

Before any model run, static analysis was run over the dataset and every finding that matched no label
was examined. Accidental issues were removed from the files; two static false positives in clean files
were kept on purpose, because they are the kind the controls exist to measure.

The files are excluded from this repository's own linting and secret scanning (see
`.pre-commit-config.yaml`): the bugs and the fake signing key are the point.

## Reproducing

From `backend/`, with keys in `backend/.env` for the model runs:

```bash
uv run python -m evaluation check                      # validate labels against files
uv run python -m evaluation run static                 # A
uv run python -m evaluation run llm-only               # B
uv run python -m evaluation run hybrid                 # D and E
uv run python -m evaluation run model --provider nvidia --rounds 10    # F, one per provider
uv run python -m evaluation score                      # scores.json and tables.md
uv run python -m evaluation routing                    # router simulation, no keys needed
uv run python -m evaluation latency                    # end-to-end timings
```

Runs resume: files already complete are skipped, and failed files are retried. `--rounds` waits out
rate-limit pauses for single-provider runs. `--fresh` starts over. Scoring needs no keys, so anyone can
re-score the committed runs.

## Human ratings

`human_eval/rating_sheet.csv` lists AI suggestions sampled from configuration E, without the model's
name. Each rater copies it to `human_eval/ratings_<name>.csv` and scores every item from 1 (poor) to 5
(excellent) on:

- **correctness**: the issue is real and the explanation is right;
- **usefulness**: acting on it would improve the code;
- **clarity**: it is easy to understand what to change and why.

Then run `uv run python -m evaluation agreement` for means per model and inter-rater agreement
(weighted Cohen's kappa per pair, Fleiss' kappa for three or more raters).
