"""LLM review: context building, model answers, grounding, verification and merging.

Static findings and code chunks go in; findings that are grounded in the code,
judged by a model and, when serious, checked by a second model come out. Code
is masked for secrets before any of it reaches a prompt.
"""
