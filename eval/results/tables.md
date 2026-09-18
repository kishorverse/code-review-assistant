Dataset: seeded v1, 32 files (10 clean), 55 labels.

## Ablation with one reviewer (NVIDIA, review task)

| Config | Description | Files | Reported | Precision | Recall | F1 | Macro-F1 | Clean-file FPs | Recall (static-type) | Recall (semantic) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | Static analysis only | 32/32 | 33 | 0.94 | 0.53 | 0.68 | 0.82 | 2 | 29/29 | 0/26 |
| B-nvidia | LLM only (no static context) | 32/32 | 50 | 0.82 | 0.73 | 0.77 | 0.88 | 3 | 18/29 | 22/26 |
| D-nvidia | Hybrid: static context + LLM review | 32/32 | 65 | 0.88 | 0.93 | 0.90 | 0.93 | 2 | 29/29 | 22/26 |
| E-nvidia+local | Hybrid + cross-check by the local model | 32/32 | 65 | 0.88 | 0.93 | 0.90 | 0.93 | 2 | 29/29 | 22/26 |

## Ablation as routed (every provider, review and style)

| Config | Description | Files | Reported | Precision | Recall | F1 | Macro-F1 | Clean-file FPs | Recall (static-type) | Recall (semantic) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | Static analysis only | 32/32 | 33 | 0.94 | 0.53 | 0.68 | 0.82 | 2 | 29/29 | 0/26 |
| B | LLM only, routed | 32/32 | 38 | 0.61 | 0.42 | 0.49 | 0.35 | 2 | 12/29 | 11/26 |
| D | Hybrid, routed | 32/32 | 89 | 0.57 | 0.84 | 0.68 | 0.62 | 7 | 29/29 | 17/26 |
| E | Hybrid + cross-check, routed | 32/32 | 89 | 0.57 | 0.84 | 0.68 | 0.62 | 7 | 29/29 | 17/26 |

## Per category (F1, with precision / recall)

| Category | A | B-nvidia | D-nvidia | E-nvidia+local | B | D | E |
|---|---|---|---|---|---|---|---|
| bug | 0.52 (1.00 / 0.35, n=23) | 0.78 (0.74 / 0.83, n=23) | 0.83 (0.79 / 0.87, n=23) | 0.83 (0.79 / 0.87, n=23) | 0.65 (0.70 / 0.61, n=23) | 0.73 (0.69 / 0.78, n=23) | 0.73 (0.69 / 0.78, n=23) |
| maintainability | 1.00 (1.00 / 1.00, n=2) | — (— / 0.00, n=2) | 1.00 (1.00 / 1.00, n=2) | 1.00 (1.00 / 1.00, n=2) | 0.00 (0.00 / 0.00, n=2) | 0.21 (0.12 / 1.00, n=2) | 0.21 (0.12 / 1.00, n=2) |
| performance | — (— / 0.00, n=7) | 0.93 (0.88 / 1.00, n=7) | 0.89 (0.80 / 1.00, n=7) | 0.89 (0.80 / 1.00, n=7) | — (— / 0.00, n=7) | 0.67 (0.80 / 0.57, n=7) | 0.67 (0.80 / 0.57, n=7) |
| security | 0.84 (0.88 / 0.80, n=15) | 0.93 (0.93 / 0.93, n=15) | 1.00 (1.00 / 1.00, n=15) | 1.00 (1.00 / 1.00, n=15) | 0.75 (1.00 / 0.60, n=15) | 0.94 (0.94 / 0.93, n=15) | 0.94 (0.94 / 0.93, n=15) |
| style | 0.93 (1.00 / 0.88, n=8) | — (— / 0.00, n=8) | 0.93 (1.00 / 0.88, n=8) | 0.93 (1.00 / 0.88, n=8) | 0.00 (0.00 / 0.00, n=8) | 0.57 (0.40 / 1.00, n=8) | 0.57 (0.40 / 1.00, n=8) |

## Security recall per CWE

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

## Model comparison (review task only, one provider each)

| Config | Model | Files | Model findings | Precision (model findings) | Semantic labels found | Recall (with static) | F1 (with static) | Clean-file FPs (model) | Answered p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| F-nvidia | `nvidia/nemotron-3-super-120b-a12b` | 32/32 | 53 | 0.85 | 22/26 | 0.93 | 0.90 | 2 | 29646 / 69391 |
| F-gemini | `gemini-3.5-flash` | 29/32 | 49 | 0.94 | 23/24 | 0.98 | 0.96 | 0 | 7741 / 21374 |
| F-hf-large | `openai/gpt-oss-120b` | 17/32 | 36 | 0.89 | 16/18 | 0.95 | 0.93 | 2 | 1334 / 2182 |
| F-local | `qwen3-vl:4b-instruct` | 32/32 | 24 | 0.83 | 0/26 | 0.47 | 0.61 | 2 | 7681 / 31309 |

## Model comparison on the files every model completed

17 files, the same for every model.

| Config | Model | Files | Model findings | Precision (model findings) | Semantic labels found | Recall (with static) | F1 (with static) | Clean-file FPs (model) | Answered p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| F-nvidia | `nvidia/nemotron-3-super-120b-a12b` | 17/17 | 32 | 0.84 | 15/18 | 0.92 | 0.90 | 1 | 30375 / 82235 |
| F-gemini | `gemini-3.5-flash` | 17/17 | 36 | 0.92 | 17/18 | 0.97 | 0.95 | 0 | 9231 / 21815 |
| F-hf-large | `openai/gpt-oss-120b` | 17/17 | 36 | 0.89 | 16/18 | 0.95 | 0.93 | 2 | 1334 / 2182 |
| F-local | `qwen3-vl:4b-instruct` | 17/17 | 14 | 0.86 | 0/18 | 0.47 | 0.62 | 2 | 9169 / 28485 |

## Cross-model verification

| Config | Confirmed | of them labeled issues | Disputed (flagged for review) | of them false positives | Precision as reported | Precision if disputed were hidden |
|---|---|---|---|---|---|---|
| E-nvidia+local | 30 | 24 | 2 | 0 | 0.88 | 0.87 |
| E | 6 | 6 | 0 | 0 | 0.57 | 0.57 |

## Cost and routing

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

## Labels found

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
