# LLM Routing

Every model call in Margin goes through one router (`backend/app/llm/router.py`). It picks a provider suited to the task, stays inside each provider's rate limits, and falls back to another provider when one fails. It also enforces the privacy rule that code only reaches a hosted provider with consent.

## Providers

| Name | Client | Where it runs | Enabled when `.env` sets |
|---|---|---|---|
| `nvidia` | OpenAI-compatible (`integrate.api.nvidia.com`) | Hosted | `NVIDIA_API_KEY`, `NVIDIA_MODEL` |
| `gemini` | Gemini REST API (`generateContent`) | Hosted | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| `hf-large` | OpenAI-compatible (`router.huggingface.co`) | Hosted | `HF_TOKEN`, `HF_MODEL_LARGE` |
| `hf-small` | OpenAI-compatible (`router.huggingface.co`) | Hosted | `HF_TOKEN`, `HF_MODEL_SMALL` |
| `local` | OpenAI-compatible (Ollama by default) | This machine | `LOCAL_MODEL` (and `LOCAL_BASE_URL` if not Ollama's default) |

- **Model ids** are not hard-coded. `uv run python scripts/list_models.py` lists the ids each key can use, plus the models on a running local server.
- **No vendor SDKs.** Providers are called directly with `httpx`, which gives four things:
  - one set of timeouts for every provider
  - no hidden SDK retries competing with the router
  - every failure mapped precisely onto one error hierarchy
  - every client testable with recorded HTTP responses (`respx`)
- **Mock mode.** `LLM_MODE=mock` replaces every provider with an in-process mock of the same name and privacy flag, and turns rate limits off. Tests, CI and demos then exercise the full routing path offline.

## Task routing

Each task has an ordered preference list in `backend/config/providers.yaml`:

| Task | Order | Reasoning |
|---|---|---|
| `review` | nvidia → gemini → hf-large → local | The most calls (one per chunk), so the most generous rate limit goes first. |
| `style` | hf-small → nvidia → gemini → local | Style needs less reasoning; a small model is enough and cheap. |
| `verify` | gemini → hf-large → nvidia → local | A different model family from the main reviewer. The provider that reported a finding is always excluded from verifying it. |
| `summarize` | gemini → nvidia → hf-large → local | One call per scan, over the longest context. |

The local model is last on every list. It is the fallback when hosted providers are unavailable, and the only candidate when code must not leave the machine.

A request can narrow the list further:

- **`allow_external`** (default `false`) is the consent gate. Without it, hosted providers are never called. A `local` server whose URL is not a loopback address counts as hosted.
- **`exclude_providers`** removes providers, for example the reviewer of a finding under verification.
- **`only_providers`** restricts the request to the named providers, even ones outside the task's usual list. The evaluation uses it to compare models.

## What happens on each attempt

For each candidate in order:

1. **Breaker open?** If a recent failure paused the provider, it is skipped.
2. **Rate limits.** The router computes how long the request would have to wait for capacity. If that is longer than `interactive_max_wait_seconds` (5 s) or `batch_max_wait_seconds` (30 s), it moves on to the next provider instead of waiting.
3. **Reserve and wait.** One request and the estimated tokens (prompt size plus the output budget) are reserved, then the router sleeps if needed.
4. **Concurrency slot.** Batch requests queue for one of the provider's `max_concurrency` slots. Interactive requests give up once their wait budget is spent and try the next provider.
5. **Admission.** Only now is the breaker asked whether to call, because the provider may have been paused while the request waited. A paused provider is skipped instead of being piled onto. A provider whose pause just ended receives a single recovery probe; other requests skip it until the probe reports back or the provider's timeout passes. A request dropped here gives its reservation back.
6. **Call** with the provider's timeout. The reservation is then settled against the usage the provider reports: unused tokens are returned, and usage beyond the estimate is charged.

Every attempt produces a `CallRecord`: provider, model, status, latency, token counts and a short reason. Records never contain prompts or responses. If no provider succeeds, the router raises `AllProvidersUnavailableError` carrying every record, and the pipeline continues with static findings only.

## Failures and pauses

| Failure | Status | Pause |
|---|---|---|
| HTTP 429 with `Retry-After`, or a Gemini `RetryInfo` delay | `rate_limited` | Exactly the requested delay |
| HTTP 429 without a delay | `rate_limited` | Exponential: 2 s, 4 s, 8 s … capped at 60 s |
| Gemini daily quota (a `QuotaFailure` naming a per-day quota) | `quota_exhausted` | Until midnight Pacific time, when the quota resets |
| HTTP 402 (Hugging Face credits used up) | `quota_exhausted` | 1 hour, then a probe |
| HTTP 401 / 403, or Gemini's HTTP 400 `API_KEY_INVALID` | `auth_failed` | 1 hour; a rejected key will not start working by itself |
| HTTP 404, an invalid base URL, or a key that cannot be sent | `misconfigured` | 1 hour; fix the model id or `*_BASE_URL` |
| Timeout, connection error, HTTP 408 / 5xx, or a response that is not the API's JSON | `unavailable` | 30 s after 3 failures without a success in between |
| Any other 4xx, a blocked prompt, an empty answer, or an answer cut off at the output token limit | `rejected` | None: the problem is this request, so the next provider is tried and the provider keeps serving other requests |

A truncated answer is never returned or cached, even if some text came back.

Tokens reserved for a request the provider refused without processing it (429, 402, 401/403, 404) are returned to the budget.

Calls run concurrently, so outcomes can arrive out of order. A pause is never shortened by a later, shorter one (a 5 s rate limit does not end a daily-quota pause), and a success from a call that started before a pause does not end it.

## Rate limits

Each provider has token buckets for requests per minute, tokens per minute and requests per day. Buckets refill continuously and are sized at `safety` × the configured limit (0.8 by default). Reservations may take a bucket into debt, so concurrent requests never overspend it. Providers that draw on one account (`hf-large` and `hf-small`) share one set of buckets.

The limits in `providers.yaml` are conservative defaults:

- **Gemini:** Google shows each key's limits only in [AI Studio](https://aistudio.google.com/rate-limit). Copy your key's values into the file.
- **NVIDIA:** the build.nvidia.com free tier allows about 40 requests per minute per model.
- **Hugging Face:** bills monthly credits instead of publishing request limits.

Limits that are set too high cost one refused request, after which the breaker takes over. They do not cost a failed scan.

## Response cache

Successful responses are cached in memory (512 entries by default, least recently used evicted). The key is a SHA-256 over the task, both prompts, JSON mode, temperature and the output budget.

The provider is not part of the key, but a cached answer is only served if its provider would be allowed to handle the new request. An answer from a hosted model is never returned to a local-only request, and never to a verification request that excludes that model.

## Configuration reference

`backend/config/providers.yaml` is validated when the router is built. The following are configuration errors, not silent misbehaviour:

- a typo in a key
- an unknown provider name
- a route naming an unconfigured provider
- a provider listed twice in one route
- a task without a route

| Section | Field | Meaning |
|---|---|---|
| `limits.<group>` | `requests_per_minute`, `tokens_per_minute`, `requests_per_day` | A budget; leave a field out for no limit. |
| `providers.<name>` | `limits` | Which budget the provider draws on. |
| | `max_concurrency` | Concurrent calls (1 for a local model). |
| | `timeout_seconds` | Upper bound on one call. |
| | `json_mode` | Send `response_format: json_object`; turn off for servers that reject it. |
| `routing.<task>` | list | Provider order for the task. |
| `router` | `safety`, `interactive_max_wait_seconds`, `batch_max_wait_seconds`, `cache_entries` | Router-wide behaviour. |
