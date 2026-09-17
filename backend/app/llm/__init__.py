"""LLM access: providers, rate limiting, circuit breakers, caching and routing.

Every model call goes through :class:`~app.llm.router.Router`, which picks a
provider suited to the task, stays inside each provider's rate limits and falls
back to another provider when one is unavailable. Code reaches an external
provider only when a request explicitly allows it.
"""
