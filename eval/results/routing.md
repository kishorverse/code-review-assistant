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
