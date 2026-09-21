# Evaluation

How well Margin finds real issues, what the models add to static analysis, how the router copes with
free-tier limits, and how long scans take. Every number below comes from the runs committed in
`eval/results/`, and can be recomputed without API keys (see [Reproducing](#10-reproducing)).

## Summary

- **The hybrid is what makes Margin work.** With one reviewer model throughout, static analysis alone
  reached F1 0.68 (precision 0.94, recall 0.53) and found none of the 26 semantic issues; the model alone
  reached 0.77; static analysis plus the model reached **0.90** (precision 0.88, recall 0.93), keeping
  every rule-shaped issue and 22 of the 26 semantic ones.
- **Models differ a lot, and free tiers decide which can be used.** Gemini 3.5 Flash was the most
  accurate (17 of 18 semantic issues on the files every model completed, 92 % precision), gpt-oss-120b
  the fastest (1.3 s per answer), NVIDIA's Nemotron the only one whose free tier could review
  everything, and a 4B local model found none of the semantic issues.
- **A verifier must be strong.** The local model as verifier confirmed false positives and disputed
  real issues.
- **The router keeps scans alive.** In a simulated outage a plain client completes nothing and the
  router completes every call; in a burst it avoids every 429. In the live runs, 732 model calls met
  overloaded providers, spent quotas and timeouts, and no scan failed.
- **Static scans take seconds; hybrid scans minutes**, dominated by the models' answer times.
- **Real repositories do not break it, but they do flood it.** Six third-party projects in five
  languages (981 files, 172 KLOC) scanned without a crash, at 350 to 1,600 files a minute; mature
  libraries came out at one to two findings per KLOC. Two defaults are wrong for real code, though:
  PEP 8's 79 columns against projects formatted at 88, and detect-secrets on test fixtures (section 6).
- **Free tiers are the weak point.** Run as routed while quotas were spent, the hybrid fell back to the
  local model for some tasks: recall stayed at 0.84, but precision dropped to 0.57.
- **The evaluation found five real problems in Margin**, all fixed (section 7).
- Human usefulness ratings are prepared but not yet collected.


## 1. Method

### Dataset

The seeded dataset (`eval/datasets/seeded/`) is 32 Python modules written for this evaluation, so no
model can have seen them in training:

- **22 files with 55 injected issues:** 15 security issues with CWE ids, 21 bugs, 2 type errors, 7
  performance problems, 8 PEP 8 / PEP 257 style deviations and 2 maintainability issues.
- **10 clean controls.** Several look risky but are safe: a parameterized query, a path join checked
  against its root, an argument-list subprocess, constant-time token checks, a SHA-256 fingerprint of a
  random token. Every finding in them is a false positive.

Each label says, decided when it was written, whether a static analyzer should find the issue
(**static-type**, 29 labels) or it takes understanding the code (**semantic**, 26 labels: an offset
off by one page, a discount applied twice, an LRU cache evicting its newest entry, a retry loop that
never counts, a path join that lets `..` escape, server-side fetches of user URLs, and so on).

Before any model ran, static analysis was run over the dataset and every unmatched finding examined.
Accidental issues (a line one character too long, an unrelated `PERF401` hint) were removed; two static
false positives in clean files were kept, because measuring them is what the controls are for. This
curation found a real bug, now fixed: Ruff 0.16 reports syntax errors as `invalid-syntax`, which Margin
classified as style instead of a bug.

### Configurations

| Config | What runs |
|---|---|
| A | Static analysis only |
| B-nvidia | LLM review only: NVIDIA's model sees the code but no static findings |
| D-nvidia | Hybrid: static findings and metrics go to NVIDIA's model as context, and grounding checks every AI finding |
| E-nvidia+*verifier* | D-nvidia's findings of medium severity and up, cross-checked by a model from another provider |
| F-*model* | The hybrid review with a single model, one run per model (F-nvidia is D-nvidia) |
| B, D, E | The product as it routes: every provider by its preference order, with review and style tasks; E cross-checks high and critical AI findings |

The first ablation pins the reviewer to one model, so its differences come from the configuration. The
pinned and single-model runs cover the review task (bugs, security, performance) and leave style review
out to fit free-tier quotas; the routed runs include it. In the routed runs each call went to whichever
provider was preferred and available, so the model that answered varies; every call is recorded.

Each file was scanned on its own, as a single-file upload, with the product's defaults: standard depth,
AI-only findings reported from confidence 0.6. Only findings the product would report count: rejected
and AI-dismissed findings and low-confidence AI findings do not. All runs used prompt version 1 and
took place on 18 September 2026.

### Matching and metrics

A finding matches a label when it is in the same file, its lines overlap the label's within two lines,
and its category agrees (a type error counts as a bug). **Precision** is the share of reported findings
that point at a labeled issue. **Recall** is the share of labels found, pairing findings and labels one
to one (a maximum bipartite matching), so one finding cannot count for two nearby issues. **F1** is
their harmonic mean; **macro-F1** averages F1 over the categories. **Style accuracy** is precision,
recall and F1 on the style labels. A configuration is scored on the files it completed: a file whose
review failed because a quota ran out would otherwise count as the model finding nothing.

## 2. Results: what the models add

### Ablation with one reviewer

NVIDIA's Nemotron 3 Super reviewed every file, alone, in every model configuration, so the differences
come from the configuration and not from which provider happened to answer.

<!-- TABLE:pinned -->
| Config | Description | Files | Reported | Precision | Recall | F1 | Macro-F1 | Clean-file FPs | Recall (static-type) | Recall (semantic) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | Static analysis only | 32/32 | 33 | 0.94 | 0.53 | 0.68 | 0.82 | 2 | 29/29 | 0/26 |
| B-nvidia | LLM only (no static context) | 32/32 | 50 | 0.82 | 0.73 | 0.77 | 0.88 | 3 | 18/29 | 22/26 |
| D-nvidia | Hybrid: static context + LLM review | 32/32 | 65 | 0.88 | 0.93 | 0.90 | 0.93 | 2 | 29/29 | 22/26 |
| E-nvidia+local | Hybrid + cross-check by the local model | 32/32 | 65 | 0.88 | 0.93 | 0.90 | 0.93 | 2 | 29/29 | 22/26 |
<!-- /TABLE -->

- **Static analysis is precise but blind to meaning.** It finds every issue a rule can express and none
  of the 26 that need understanding: the off-by-one page, the discount applied twice, the cache that
  evicts its newest entry.
- **The model finds the semantic issues either way.** With or without static context, NVIDIA found 22
  of the 26. Static context did not make it find more of them.
- **The hybrid keeps both.** It reports everything static analysis finds plus what the model finds, at
  higher precision than the model alone (0.88 against 0.82). Without static context the model also
  missed two rule-shaped issues (a request without a timeout, `return` inside `finally`).
- **B cannot find style issues by design:** the single-provider runs leave style review out, so its
  static-type recall includes 9 style and maintainability labels it never looked for. On the review
  task's own categories, the hybrid is ahead for bugs (F1 0.83 against 0.78) and security (1.00 against
  0.93), and slightly behind for performance (0.89 against 0.93).

Per category, for every configuration:

<!-- TABLE:categories -->
| Category | A | B-nvidia | D-nvidia | E-nvidia+local | B | D | E |
|---|---|---|---|---|---|---|---|
| bug | 0.52 (1.00 / 0.35, n=23) | 0.78 (0.74 / 0.83, n=23) | 0.83 (0.79 / 0.87, n=23) | 0.83 (0.79 / 0.87, n=23) | 0.65 (0.70 / 0.61, n=23) | 0.73 (0.69 / 0.78, n=23) | 0.73 (0.69 / 0.78, n=23) |
| maintainability | 1.00 (1.00 / 1.00, n=2) | — (— / 0.00, n=2) | 1.00 (1.00 / 1.00, n=2) | 1.00 (1.00 / 1.00, n=2) | 0.00 (0.00 / 0.00, n=2) | 0.21 (0.12 / 1.00, n=2) | 0.21 (0.12 / 1.00, n=2) |
| performance | — (— / 0.00, n=7) | 0.93 (0.88 / 1.00, n=7) | 0.89 (0.80 / 1.00, n=7) | 0.89 (0.80 / 1.00, n=7) | — (— / 0.00, n=7) | 0.67 (0.80 / 0.57, n=7) | 0.67 (0.80 / 0.57, n=7) |
| security | 0.84 (0.88 / 0.80, n=15) | 0.93 (0.93 / 0.93, n=15) | 1.00 (1.00 / 1.00, n=15) | 1.00 (1.00 / 1.00, n=15) | 0.75 (1.00 / 0.60, n=15) | 0.94 (0.94 / 0.93, n=15) | 0.94 (0.94 / 0.93, n=15) |
| style | 0.93 (1.00 / 0.88, n=8) | — (— / 0.00, n=8) | 0.93 (1.00 / 0.88, n=8) | 0.93 (1.00 / 0.88, n=8) | 0.00 (0.00 / 0.00, n=8) | 0.57 (0.40 / 1.00, n=8) | 0.57 (0.40 / 1.00, n=8) |
<!-- /TABLE -->

Security recall per CWE (labels found):

<!-- TABLE:cwe -->
| CWE | Labels | A | B-nvidia | D-nvidia | E-nvidia+local | B | D | E |
|---|---|---|---|---|---|---|---|---|
| CWE-208 | 1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| CWE-22 | 2 | 1/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| CWE-295 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| CWE-330 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| CWE-400 | 1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| CWE-502 | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| CWE-78 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| CWE-79 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| CWE-798 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| CWE-89 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| CWE-916 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| CWE-918 | 1 | 0/1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| CWE-95 | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
<!-- /TABLE -->

### Cross-model verification

Verification re-checks each AI finding of medium severity or above with a model from another provider.
A disputed finding stays in the report, flagged for human review, so verification changes no score by
itself; what matters is whether it flags the right findings.

<!-- TABLE:verification -->
| Config | Confirmed | of them labeled issues | Disputed (flagged for review) | of them false positives | Precision as reported | Precision if disputed were hidden |
|---|---|---|---|---|---|---|
| E-nvidia+local | 30 | 24 | 2 | 0 | 0.88 | 0.87 |
| E | 6 | 6 | 0 | 0 | 0.57 | 0.57 |
<!-- /TABLE -->

The local 4B model was the only verifier available once Gemini's daily quota was used, and it is not
useful: it confirmed 30 findings, 6 of them false positives, and its only two disputes were real issues.
A verifier has to be at least as strong as the reviewer. The run with Gemini as the verifier could not
be made: its daily quota was spent on the model comparison.

### Model comparison

Each model reviewed the files alone (the review task, with static context), as far as its free tier
allowed. Precision is over the findings the model reported or confirmed.

<!-- TABLE:models -->
| Config | Model | Files | Model findings | Precision (model findings) | Semantic labels found | Recall (with static) | F1 (with static) | Clean-file FPs (model) | Answered p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| F-nvidia | `nvidia/nemotron-3-super-120b-a12b` | 32/32 | 53 | 0.85 | 22/26 | 0.93 | 0.90 | 2 | 29646 / 69391 |
| F-gemini | `gemini-3.5-flash` | 29/32 | 49 | 0.94 | 23/24 | 0.98 | 0.96 | 0 | 7741 / 21374 |
| F-hf-large | `openai/gpt-oss-120b` | 17/32 | 36 | 0.89 | 16/18 | 0.95 | 0.93 | 2 | 1334 / 2182 |
| F-local | `qwen3-vl:4b-instruct` | 32/32 | 24 | 0.83 | 0/26 | 0.47 | 0.61 | 2 | 7681 / 31309 |
<!-- /TABLE -->

- **Gemini 3.5 Flash was the most accurate**: 23 of the 24 semantic issues in the files it completed,
  94 % of its findings real, and nothing reported in the clean files. Its free tier (5 requests a
  minute, about 30 a day) is its limit: it completed 29 of the 32 files before the daily quota ran out.
- **gpt-oss-120b was nearly as good and by far the fastest** (1.3 s median), until Hugging Face
  reported the account's monthly credits used up, after 17 files.
- **Nemotron found 22 of 26 at 85 % precision**, and it is the only hosted model whose free tier could
  review everything; it was also the slowest (30 s median, 70 s at p95) and often overloaded.
- **The local 4B model found none of the semantic issues.** It mostly judged static findings and
  proposed two new ones in 32 files. It is a privacy fallback, not a reviewer.

Quotas stopped two models early, so the table above compares different sets of files. On the 17 files
every model completed, the ranking is the same:

<!-- TABLE:models-common -->
17 files, the same for every model.

| Config | Model | Files | Model findings | Precision (model findings) | Semantic labels found | Recall (with static) | F1 (with static) | Clean-file FPs (model) | Answered p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| F-nvidia | `nvidia/nemotron-3-super-120b-a12b` | 17/17 | 32 | 0.84 | 15/18 | 0.92 | 0.90 | 1 | 30375 / 82235 |
| F-gemini | `gemini-3.5-flash` | 17/17 | 36 | 0.92 | 17/18 | 0.97 | 0.95 | 0 | 9231 / 21815 |
| F-hf-large | `openai/gpt-oss-120b` | 17/17 | 36 | 0.89 | 16/18 | 0.95 | 0.93 | 2 | 1334 / 2182 |
| F-local | `qwen3-vl:4b-instruct` | 17/17 | 14 | 0.86 | 0/18 | 0.47 | 0.62 | 2 | 9169 / 28485 |
<!-- /TABLE -->

These rankings decide the routing: see [model selection](model_selection.md).

### Usefulness, rated by people

Matching findings to labels measures whether a finding is right, not whether its suggestion helps. For
that, `eval/human_eval/rating_sheet.csv` holds 26 suggestions sampled evenly from the four models (8
each from Gemini, Nemotron and gpt-oss; the local model wrote only 2), shuffled and without the model's
name. Raters score each for correctness, usefulness and clarity from 1 to 5, and
`python -m evaluation agreement` reports means per model with weighted Cohen's and Fleiss' kappa.
**The ratings have not been collected yet**; this section will report them once two or three reviewers
have filled in the sheet.

## 3. Results: style accuracy

Style is where static analysis is strongest. Ruff (PEP 8) found 7 of the 8 style labels with no false
positives (F1 0.93); the eighth, a public function without a docstring (PEP 257), is not a rule Margin
enables, and no model reported it either.

With LLM style review added (the routed hybrid run, D), every style label was found, including the
missing docstring, but style precision fell to 0.40 and maintainability precision to 0.12: most style
tasks fell back to the local 4B model (see below), which reports many low-value remarks. Static
analysis is the better style checker here; LLM style review is only worth its noise with a strong
model behind it.

## 4. Results: routing

### Simulation

`python -m evaluation routing` replays 120 review calls against simulated providers with the limits of
the real free tiers, comparing Margin's router (its real limiter and breakers) with two plain clients.
A time-scaled clock makes each simulated minute last a second.

<!-- TABLE:routing -->
| Scenario | Strategy | Completed | Failed | 429s received | Served by fallback | Simulated minutes |
|---|---|---|---|---|---|---|
| burst | naive | 80/120 | 40 | 178 | 0 | 1.9 |
| burst | retry-after | 120/120 | 0 | 12 | 0 | 2.4 |
| burst | router | 120/120 | 0 | 0 | 18 | 3.1 |
| outage | naive | 0/120 | 120 | 0 | 0 | 2.9 |
| outage | retry-after | 0/120 | 120 | 0 | 0 | 2.8 |
| outage | router | 120/120 | 0 | 0 | 120 | 4.2 |
| wrong-limits | naive | 80/120 | 40 | 174 | 0 | 1.9 |
| wrong-limits | retry-after | 120/120 | 0 | 12 | 0 | 2.4 |
| wrong-limits | router | 120/120 | 0 | 2 | 40 | 2.2 |

- **burst**: 120 review calls; NVIDIA-like 40 RPM preferred, Gemini-like 5 RPM and Hugging Face-like 30 RPM as fallbacks.
- **outage**: as burst, but the preferred provider answers every call with 503.
- **wrong-limits**: as burst, but the router believes the preferred provider allows 60 RPM when it allows 40.
<!-- /TABLE -->

- In a **burst**, the naive client loses a third of the calls to 429s. The router completes all of
  them without a single 429, moving 18 to fallback providers rather than waiting.
- In an **outage** of the preferred provider, both plain clients complete nothing; the router
  completes every call through the fallbacks.
- With **limits configured too high**, the router takes two 429s, pauses the provider for as long as
  it asked, and finishes faster than the client that only retries.

The simulation found a real bug. The first version of the limiter used token buckets for requests; a
bucket that starts full and refills while it is spent lets through up to twice its limit in the first
minute, which the simulated fallback providers answered with 429s, so in the outage scenario only 35 of
120 calls completed. The live runs showed the same thing against Gemini's free tier (5 requests a
minute). Requests are now counted in sliding windows; the numbers above are after the fix.

### Live runs

The routed configurations run the product as it is: every provider in its preference order, review and
style tasks, cross-checks of high and critical AI findings. On the day of the runs Gemini's quota was
spent on the model comparison and Hugging Face's credits ran out, so the routed hybrid run (D, E) got
its reviews from NVIDIA for 25 files and from the local model for 7 (after NVIDIA 503s), and 18 of its
32 style tasks from the local model.

<!-- TABLE:routed -->
| Config | Description | Files | Reported | Precision | Recall | F1 | Macro-F1 | Clean-file FPs | Recall (static-type) | Recall (semantic) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | Static analysis only | 32/32 | 33 | 0.94 | 0.53 | 0.68 | 0.82 | 2 | 29/29 | 0/26 |
| B | LLM only, routed | 32/32 | 38 | 0.61 | 0.42 | 0.49 | 0.35 | 2 | 12/29 | 11/26 |
| D | Hybrid, routed | 32/32 | 89 | 0.57 | 0.84 | 0.68 | 0.62 | 7 | 29/29 | 17/26 |
| E | Hybrid + cross-check, routed | 32/32 | 89 | 0.57 | 0.84 | 0.68 | 0.62 | 7 | 29/29 | 17/26 |
<!-- /TABLE -->

Routed, the hybrid still found every rule-shaped issue and 17 of 26 semantic ones (recall 0.84), but
precision dropped to 0.57, almost all of it from the local model's style and maintainability remarks.
The routed LLM-only run (B) was served mostly by the local model and is shown for completeness; it was
measured before the style-budget fix below, while the routed hybrid run was repeated after it.

The lesson for the product is in the routing, not the pipeline: on exhausted free tiers, a hosted
scan should skip a task rather than hand it to a model this weak. Making that a routing option is the
first item of future work.

## 5. Results: latency

`python -m evaluation latency` times whole scans, as the CLI runs them, of generated 50, 200 and
500-line files (five static and three hybrid runs each) and of the 32-file seeded project, with a fresh
router each time so no answer comes from the cache. Hybrid scans ran at standard depth with every
provider as routed; Gemini's daily quota was already used, so its tasks fell back.

<!-- TABLE:latency -->
Measured 2026-09-18 10:53 UTC. Times in seconds; stage columns are medians.

| Input | Mode | Runs | p50 | p95 | Analyzers | Review | Cross-check | Summary | Model calls | Files per minute |
|---|---|---|---|---|---|---|---|---|---|---|
| 50 lines | static | 5 | 2.8 | 3.1 | 2.8 | 0.0 | 0.0 | 0.0 | 0 | 21.2 |
| 50 lines | hybrid | 3 | 38.5 | 52.7 | 3.0 | 12.9 | 0.0 | 17.5 | 4 | 1.6 |
| 200 lines | static | 5 | 3.4 | 4.5 | 3.4 | 0.0 | 0.0 | 0.0 | 0 | 17.5 |
| 200 lines | hybrid | 3 | 105.5 | 128.9 | 3.5 | 92.8 | 0.0 | 13.2 | 6 | 0.6 |
| 500 lines | static | 5 | 4.3 | 5.6 | 4.3 | 0.0 | 0.0 | 0.0 | 0 | 13.8 |
| 500 lines | hybrid | 3 | 76.5 | 77.5 | 3.8 | 52.7 | 0.0 | 19.7 | 14 | 0.8 |
| 32-file project | static | 1 | 4.2 | 4.2 | 4.1 | 0.0 | 0.0 | 0.0 | 0 | 458.2 |
| 32-file project | hybrid | 1 | 607.3 | 607.3 | 5.0 | 531.0 | 52.9 | 18.4 | 158 | 3.2 |
<!-- /TABLE -->

- **Static analysis is fast and flat**: 3 to 4 seconds a file whatever its size, mostly tool start-up,
  and the whole 32-file project in about 4 seconds, because the analyzers run once over the project,
  in parallel.
- **Model calls dominate a hybrid scan.** A 50-line file takes about 40 seconds, a few hundred lines one
  to two minutes, and the 32-file project 10 minutes (about 3 files a minute, 158 call attempts).
  Nemotron's median answer is 30 seconds, and 503s and timeouts add retries on other providers; the
  200-line file took longer than the 500-line one only because of that variance.
- **For CI, static depth is the default** (seconds per project); LLM review is worth its minutes when a
  person will read the results, which is how the web UI and the Action's `MARGIN_DEPTH` are meant to
  be used. gpt-oss answered in 1.3 seconds median, so paid capacity on a fast provider would cut hybrid
  scans to a fraction of this.


## 6. Robustness

Every number in this report came through the conditions the router exists for:

- **No scan crashed.** 448 file scans across all runs (retries included) ended with a result; a failed
  model call never failed a scan.
- **Providers failed often, and the runs finished anyway.** Of 732 model call attempts, 306 were
  answered; 350 were passed over by the router because a provider was paused or over its limit; 40 hit
  `503 overloaded` or timeouts (NVIDIA); 17 hit quotas or rate limits (Gemini's daily quota, Hugging
  Face's monthly credits); and 19 answers were rejected as unusable. Single-provider runs waited out the
  pauses in rounds; routed runs fell back to the next provider.
- **Grounding did its job.** 22 items that models reported were discarded because the lines or the code
  they quoted did not exist.
- **Broken code is still reviewed.** `upload_manifest.py` does not parse; tree-sitter's error-tolerant
  parse still chunks it, Ruff reports the syntax error (as a bug, after the fix below), and models
  reviewed the rest of the file.

### Across codebases and languages

Three codebases of this project, static analysis at the default depth, on 19 September 2026:

| Codebase | Language | Files | Findings | Seconds | Analyzers |
|---|---|---|---|---|---|
| Seeded dataset | Python | 32 | 33 | 10.0 | all 8 ran |
| Margin's backend (without tests) | Python | 115 | 18 | 8.2 | all 8 ran; the project's declared 100-column limit applied |
| Margin's frontend | TypeScript and TSX | 42 | 5 | 7.4 | the language-agnostic ones (Lizard, detect-secrets, Opengrep) |

A standard-depth review of one TSX file (`ResultsView.tsx`) ran end to end as well: Lizard's two
complexity findings were confirmed by models, and the style model added four remarks. NVIDIA was
unavailable and Gemini's and Hugging Face's quotas were spent, so its bug and security review fell back
to the local model: a working review, but a shallow one. The GitHub Action runs the same scan over the
whole repository on every push.

### Across third-party repositories

Code written by other people, for other reasons, is the harder test. Six widely used repositories, one
per supported language, each pinned to a commit and scanned by `margin scan` at the default depth with
no API keys (`uv run python -m evaluation robustness`): 981 files, 172 KLOC.

<!-- TABLE:robustness -->
Scanned 2026-09-21 UTC: static analysis only, at the default depth, with no API keys. Each repository is pinned to the commit shown.

| Repository | Language | Commit | Files | Reviewed | Languages seen | Analyzers | Seconds | Files per minute |
|---|---|---|---|---|---|---|---|---|
| psf/requests | Python | `dae7ef6` | 124 | 37 | python 37 | 8 of 8 | 6.2 | 358 |
| pallets/click | Python | `6aabf09` | 174 | 90 | python 90 | 8 of 8 | 8.4 | 643 |
| expressjs/express | JavaScript | `9a34acf` | 214 | 141 | javascript 141 | 3 of 8 | 11.7 | 723 |
| sindresorhus/got | TypeScript | `e1d87d2` | 130 | 90 | typescript 84, javascript 6 | 3 of 8 | 8.6 | 628 |
| gorilla/mux | Go | `db9d1d0` | 27 | 17 | go 17 | 2 of 8 | 2.0 | 510 |
| google/gson | Java | `854c825` | 312 | 264 | java 264 | 2 of 8 | 9.8 | 1616 |

| Repository | KLOC | Critical | High | Medium | Low | Findings per KLOC | Score | Most reported rules |
|---|---|---|---|---|---|---|---|---|
| psf/requests | 7.8 | 0 | 15 | 111 | 625 | 97 | 0/100 (E) | E501 (289), B113 (120), N802 (36) |
| pallets/click | 19.3 | 0 | 4 | 43 | 957 | 52 | 39/100 (E) | E501 (755), C408 (23), unused-variable (20) |
| expressjs/express | 21.5 | 0 | 35 | 0 | 117 | 7 | 78/100 (B) | long-function (115), Hex High Entropy String (24), Secret Keyword (6) |
| sindresorhus/got | 59.1 | 0 | 48 | 0 | 42 | 2 | 91/100 (A) | Secret Keyword (34), long-function (31), Basic Auth Credentials (11) |
| gorilla/mux | 7.5 | 0 | 0 | 0 | 15 | 2 | 98/100 (A) | long-function (11), function-complexity (4) |
| google/gson | 57.1 | 0 | 2 | 0 | 27 | 1 | 99/100 (A) | long-function (14), function-complexity (13), Secret Keyword (1) |
<!-- /TABLE -->

What it shows:

- **Nothing crashed, hung or was refused.** Every repository was ingested, preprocessed and analyzed.
  The 18 files the filters left out were binaries, minified bundles and files over 1 MB. An analyzer
  with no file of a language it reads reported *skipped* rather than failing: Ruff, Bandit, mypy, Radon
  and Vulture on the four non-Python projects, and Opengrep on Go and Java, which Margin's custom rules
  do not yet cover. That is the intended behaviour, and it is what the "Analyzers" column counts.
- **Speed holds at real sizes.** 2.0 s to 11.7 s per repository, 350 to 1,600 files a minute, on
  projects up to 59 KLOC — far beyond the brief's 500-line snippet, and still interactive.
- **On mature code the non-style analyzers are quiet.** gson scored 99/100, mux 98/100 and got 91/100:
  one to two findings per KLOC, nearly all complexity remarks. Widely reviewed code looking clean is
  the result to expect, and Margin produces it.

And two places where a first scan of a real project reports far too much:

- **Undeclared line length drowns Python repositories.** Neither requests nor click declares a line
  length, so PEP 8's 79 columns apply, while both are in fact formatted at 88. E501 alone is 289 of
  requests' 751 findings and 755 of click's 1,004, which is what drags both to grade E. Margin is
  applying the standard correctly and is still wrong in practice, because it is measuring these
  projects against a rule they never adopted.
- **detect-secrets is noisy on JavaScript and TypeScript.** 46 of got's 48 high-severity findings and
  all 35 of express's come from detect-secrets, and 78 of those 81 sit in test or fixture files:
  sample tokens, dummy credentials and high-entropy strings written to be fake. On the seeded dataset,
  where the secrets are real, the same analyzer was precise; on real repositories it is the largest
  source of high-severity noise.

Both are counted, not estimated, and both have a fix in section 9. What this benchmark does not give is
precision or recall: these repositories are unlabelled, so the tables say what Margin reports, not what
share of it is right. Labelling a sample of these findings, and running public datasets (BugsInPy,
CVEfixes), is the next step.

## 7. What the evaluation changed in Margin

The evaluation, and scanning Margin's own code while it ran, found five real problems, all fixed:

| Problem | How it showed | Fix |
|---|---|---|
| Ruff 0.16 reports syntax errors as `invalid-syntax`; Margin classified them as low-severity style | Curating the dataset | Anything that is not a rule code is a syntax error (bug, medium) |
| Isolated Ruff assumed an old Python target, so `except ExceptionGroup` was an undefined name (high) | Scanning Margin's own code | Ruff targets the Python version the upload declares, 3.11 by default |
| Request limits in token buckets allowed up to twice the limit in the first minute | 429s from Gemini's free tier; the routing simulation's outage scenario | Sliding windows for requests per minute and per day |
| Style review had half the review task's output budget; NVIDIA's reasoning ran out of it 18 times, and each fell back to the local model | Rejected calls in the routed runs | The same budget as review |
| A masked secret (`<REDACTED_SECRET_1>`) read to a model as a placeholder, and it judged a real hardcoded key a false positive | A live scan for the README screenshots | The prompts say plainly that masked values are real secrets (prompt version 2; the runs here used version 1). The rule protecting serious security findings kept the key reported |



## 8. Limitations

- **Small, synthetic dataset.** 55 labels in 32 files give wide confidence intervals: one label is
  about two points of recall. The files are realistic but short, one chunk each, so cross-file reasoning
  and chunking are not tested here.
- **Labels by one author.** Whether an issue is "static-type" or "semantic" is a judgement made before
  the runs, and matching by location and category cannot tell a right finding at the right line from a
  different, also valid remark there.
- **Free tiers shape the numbers.** Quotas ran out during the runs: Gemini's daily quota, and the
  Hugging Face account's monthly credits for the large model. Configurations therefore did not all use
  the same models, and the tables say which did.
- **Hosted models change** behind the same id. Model ids, prompt versions and dates are recorded with
  every run in `eval/results/runs/`.
- **Not measured in this round:** Gemini as the cross-check model (its quota was spent), and human
  ratings of usefulness (the sheet is ready, the ratings are not collected yet).
- **The third-party repositories are unlabelled.** Section 6 measures whether real code breaks Margin
  and how much it reports, not how much of that is right. Public datasets (BugsInPy, CVEfixes) and a
  labelled sample of these findings are left for future work.

## 9. Recommendations

In order of expected benefit:

1. **Never fall back to a much weaker model for hosted scans.** Most of the routed runs' false positives
   came from tasks that fell back to the local 4B model. A routing option to skip a task (and say so in
   the report) rather than hand it to a model below a quality bar would have kept routed precision near
   the single-reviewer 0.88.
2. **Take the line length from the formatter a project uses, not only from what it declares.** On
   requests and click, neither of which declares one, PEP 8's 79 columns produced 289 and 755 E501
   findings against code formatted at 88 — most of everything those two scans reported (section 6).
   Reading a `[tool.black]` or `[tool.ruff]` section as a declaration of its own default, or measuring
   the project's prevailing line length, would remove that flood without weakening the standard for
   projects that really do follow it.
3. **Weigh detect-secrets by where the file sits.** 78 of the 81 high-severity secret findings across
   express and got were in test and fixture files. Reporting secrets in test paths at a lower severity,
   or behind a setting, would clear the largest source of high-severity noise on real repositories
   without hiding a secret committed in production code.
4. **Use the strongest available model as the verifier, and let disputes hide findings by default.**
   The local verifier did not help; Gemini, the most accurate reviewer, is the natural verifier, and with a
   verifier that good a disputed AI-only finding could be hidden instead of only flagged.
5. **Merge AI findings into the static finding they restate.** A model sometimes files its own copy of
   an issue an analyzer already reported on the same line (a hardcoded key reported by both
   detect-secrets and the model), which costs precision without adding information.
6. **Pay for one fast provider.** gpt-oss answered in 1.3 seconds against Nemotron's 30; hybrid scans
   would drop from minutes to seconds, which is what near-real-time feedback in an editor needs.
7. **Grow the evaluation:** collect the human ratings, label a sample of the third-party findings in
   section 6, add public datasets (BugsInPy, CVEfixes), and label with more than one person.
8. **Learn from reviewers' decisions.** Accepted and rejected findings are already recorded per scan;
   feeding them back (suppressing rules a team always rejects, adding accepted examples to prompts) is
   the stretch goal the data is ready for.
9. **Offer fixes as diffs with a preview**, validated by re-running the analyzers on the patched code
   before they are shown.

## 10. Reproducing

From `backend/`:

```bash
uv run python -m evaluation score      # recompute every table from the committed runs; no keys needed
uv run python -m evaluation routing    # re-run the router simulation; no keys needed
uv run python -m evaluation robustness # re-scan the third-party repositories; needs the network
```

Re-running the model configurations needs keys in `backend/.env`; see `eval/README.md`.

## Appendix

### Every label, by configuration

<!-- TABLE:labels -->
✓ found, · missed, — file not completed by that configuration.

| Label | Category | Detection | A | B-nvidia | F-nvidia | E-nvidia+local | B | D | E | F-gemini | F-hf-large | F-local |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| user_repository/sql-injection | security | static | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | — | — | ✓ |
| user_repository/page-offset | bug | semantic | · | ✓ | ✓ | ✓ | · | ✓ | ✓ | — | — | · |
| backup_tool/shell-injection | security | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| backup_tool/tar-traversal | security | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| config_loader/unsafe-yaml | security | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| config_loader/shared-defaults | bug | semantic | · | ✓ | · | · | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| config_loader/unsafe-pickle | security | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| auth_tokens/hardcoded-key | security | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| auth_tokens/weak-random | security | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| auth_tokens/timing-compare | security | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| file_server/path-traversal | security | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| webhook_client/no-timeout | security | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | — | — | ✓ |
| webhook_client/tls-disabled | security | static | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | — | — | ✓ |
| webhook_client/ssrf | security | semantic | · | ✓ | ✓ | ✓ | · | · | · | — | — | · |
| password_store/fast-hash | security | static | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | — | ✓ |
| report_renderer/autoescape-off | security | static | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | — | ✓ |
| report_renderer/eval | security | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| inventory/mutable-default | bug | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| inventory/reorder-boundary | bug | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| inventory/is-literal | bug | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| inventory/negative-stock | bug | semantic | · | · | · | · | · | · | · | ✓ | ✓ | · |
| billing/double-discount | bug | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| billing/empty-average | bug | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| billing/cents-type | typing | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| date_ranges/end-excluded | bug | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| date_ranges/naive-now | bug | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| retry/no-increment | bug | semantic | · | ✓ | · | · | · | ✓ | ✓ | ✓ | — | · |
| retry/bare-except | bug | static | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | — | ✓ |
| page_cache/get-not-recent | bug | semantic | · | ✓ | ✓ | ✓ | · | · | · | ✓ | · | · |
| page_cache/evicts-newest | bug | semantic | · | ✓ | ✓ | ✓ | · | · | · | ✓ | ✓ | · |
| page_cache/mutate-while-iterating | bug | semantic | · | ✓ | ✓ | ✓ | · | · | · | ✓ | ✓ | · |
| csv_export/unclosed-file | maintainability | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
| csv_export/return-in-finally | bug | static | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| notifications/not-awaited | bug | static | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | · |
| notifications/blocking-sleep | performance | semantic | · | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | · |
| latency_stats/median-unsorted | bug | semantic | · | · | ✓ | ✓ | ✓ | · | · | ✓ | ✓ | · |
| latency_stats/percentile-index | bug | semantic | · | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · |
| shipping/optional-rate | typing | static | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| shipping/missing-region | bug | semantic | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | · |
| upload_manifest/syntax-error | bug | static | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | — | · |
| search_index/list-membership | performance | semantic | · | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | — | · |
| search_index/quadratic-unique | performance | semantic | · | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | — | · |
| log_scanner/compile-in-loop | performance | semantic | · | ✓ | ✓ | ✓ | · | · | · | ✓ | ✓ | · |
| log_scanner/read-whole-file | performance | semantic | · | ✓ | ✓ | ✓ | · | · | · | ✓ | ✓ | · |
| payment_matching/nested-join | performance | semantic | · | ✓ | ✓ | ✓ | · | · | · | ✓ | — | · |
| payment_matching/count-in-loop | performance | semantic | · | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ | — | · |
| legacy_helpers/multiple-imports | style | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
| legacy_helpers/unused-import | maintainability | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | · |
| legacy_helpers/function-name | style | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
| legacy_helpers/none-comparison | style | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
| legacy_helpers/class-name | style | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
| legacy_helpers/two-statements | style | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
| legacy_helpers/lambda-assignment | style | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
| legacy_helpers/missing-docstring | style | semantic | · | · | · | · | · | ✓ | ✓ | · | · | · |
| legacy_helpers/long-line | style | static | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | ✓ |
<!-- /TABLE -->

### Calls, latency and tokens per configuration

<!-- TABLE:cost -->
| Config | Calls (provider: status counts) | Answered-call latency p50 / p95 (ms) | Tokens in / out | Seconds per file p50 / p95 | Discarded items | Failed tasks |
|---|---|---|---|---|---|---|
| A | — | — | 0 / 0 | 6.8 / 10.0 | 0 | 0 |
| B-nvidia | nvidia: ok 32 | nvidia: 32382 / 67534 | 44,747 / 88,876 | 36.3 / 71.5 | 6 | 0 |
| F-nvidia | nvidia: ok 32 | nvidia: 29646 / 69391 | 49,948 / 77,953 | 33.9 / 72.4 | 7 | 0 |
| E-nvidia+local | local: ok 32 | local: 4626 / 6769 | 18,165 / 2,120 | 8.0 / 18.3 | 0 | 0 |
| B | gemini: quota_exhausted 1, skipped 54; hf-large: ok 8, quota_exhausted 1, skipped 17; hf-small: ok 3, quota_exhausted 1, skipped 28; local: ok 47; nvidia: ok 6, rejected 2, skipped 44, unavailable 9 | hf-large: 1028 / 1305; hf-small: 4128 / 5671; local: 1719 / 15733; nvidia: 20896 / 42837 | 76,639 / 25,306 | 8.5 / 93.3 | 5 | 0 |
| D | gemini: quota_exhausted 1, skipped 24; hf-large: skipped 7; hf-small: ok 1, quota_exhausted 1, skipped 30; local: ok 25; nvidia: ok 38, rejected 3, skipped 11, unavailable 11 | hf-small: 4648 / 4648; local: 1835 / 9573; nvidia: 34413 / 74658 | 87,080 / 125,232 | 57.2 / 102.4 | 5 | 0 |
| E | gemini: quota_exhausted 1, skipped 30; hf-large: ok 1, quota_exhausted 1, skipped 11; hf-small: ok 1, quota_exhausted 1, skipped 30; local: ok 30; nvidia: ok 38, rejected 3, skipped 11, unavailable 11 | hf-large: 691 / 691; hf-small: 4648 / 4648; local: 1946 / 9311; nvidia: 34413 / 74658 | 90,659 / 126,001 | 61.0 / 102.9 | 5 | 0 |
| F-gemini | gemini: ok 29 | gemini: 7741 / 21374 | 45,843 / 27,499 | 12.4 / 25.1 | 0 | 3 |
| F-hf-large | hf-large: ok 17 | hf-large: 1334 / 2182 | 26,600 / 16,256 | 4.7 / 6.3 | 0 | 15 |
| F-local | local: ok 32 | local: 7681 / 31309 | 47,573 / 2,916 | 10.9 / 36.0 | 0 | 0 |
<!-- /TABLE -->
