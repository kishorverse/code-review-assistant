# Model Selection

Which models Margin uses, for which task, and why. The choices are constrained by free tiers as much as
by quality: a model that answers well but allows twenty requests a day cannot review every chunk of a
project. The numbers here come from the [evaluation](evaluation.md) (September 2026); model ids live in
`backend/.env`, so they can be changed without touching code.

## Roles

| Task | Preference order | Why this order |
|---|---|---|
| Review (bugs, security, performance) | NVIDIA → Gemini → HF large → local | The most calls, so the most generous free tier goes first |
| Style | HF small → NVIDIA → Gemini → local | Needs less reasoning; a small, fast code model is enough |
| Verify | Gemini → HF large → NVIDIA → local | A different model family from the reviewer; the provider that reported a finding never verifies it |
| Summarize | Gemini → NVIDIA → HF large → local | One call per scan; the best writer available |

The local model comes last everywhere: it is the fallback when hosted providers are out, and the only
reviewer when the user does not consent to sending code out. Routing is in
`backend/config/providers.yaml`; how the router applies it is in [routing.md](routing.md).

## The models

| Provider | Model | Free tier as observed | Review quality (evaluation) | Speed (median answer) |
|---|---|---|---|---|
| NVIDIA NIM | `nvidia/nemotron-3-super-120b-a12b` | About 40 requests a minute, no daily cap; frequent `503 overloaded` | Found 22 of 26 semantic issues; 85 % of its findings were real | 30 s (p95 70 s) |
| Google AI Studio | `gemini-3.5-flash` | 5 requests a minute and a small daily quota (about 30 requests before `daily quota used`) | 23 of 24 semantic issues on the 29 files it completed; 94 % precision; no false positives in clean files | 8 s |
| Hugging Face | `openai/gpt-oss-120b` | Monthly credits; reported used up partway through the evaluation | 16 of 18 on the 17 files it completed; 89 % precision | 1.3 s |
| Hugging Face | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | Shares the account's credits | Style only; see the evaluation's style results | 5 s |
| Local (Ollama) | `qwen3-vl:4b-instruct` | Unlimited, on the machine | Found none of the 26 semantic issues; judges static findings, but confirmed false positives and disputed real issues when verifying | 8 s |

## Why these

**NVIDIA Nemotron reviews first** because its free tier has no daily cap: a 60-chunk scan fits in a few
minutes of its per-minute limit. It is the slowest model and often overloaded, so the router falls back
to the next provider after a 503 instead of waiting.

**Gemini verifies and summarizes.** It gave the best reviews in the evaluation, and it is a different
model family from the reviewer, which is the point of a second opinion. Its free tier cannot carry the
review load, but verification and summaries need a handful of calls per scan.

**gpt-oss-120b is the strong fallback** for review and verification: fast and nearly as accurate as
Gemini, but paid by the month through Hugging Face credits.

**A local model keeps code private** when that matters more than depth. The evaluation is clear about
the cost: a 4B model does not find semantic bugs on this dataset, and as a verifier it mostly agreed with
whatever it was shown. Margin labels which model reviewed each file, so a scan that fell back to it is
visible as such. A larger local model is the natural upgrade; none was evaluated here.

## Considered and not used

- **Llama 3.3 70B and Llama 3.1 8B** on Hugging Face, the original plan for fallback and style: gpt-oss-120b
  (a reasoning model) and Qwen3-Coder (a code model) were available on the same router and suit the
  tasks better on paper. Llama was not evaluated.
- **Gemini 2.5 Flash:** closed to new API keys. **Gemini 3.7 and 3.8 previews:** answered `503` too
  often during development to be relied on.
- **One provider for everything:** simpler, but every free tier ran out or went down at least once
  during the evaluation. Routing is what let the runs finish.

## Changing models

Put the ids in `backend/.env` (`GEMINI_MODEL`, `NVIDIA_MODEL`, `HF_MODEL_LARGE`, `HF_MODEL_SMALL`,
`LOCAL_MODEL`) and list what your keys can use with:

```bash
cd backend
uv run python scripts/list_models.py
```

After changing a model, re-run the evaluation's single-provider configuration for it
(`uv run python -m evaluation run model --provider <name> --rounds 10`) to see how it compares.
