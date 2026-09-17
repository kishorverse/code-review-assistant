{# PROMPT_VERSION: 1 #}
TASK: Review readability and style against {{ style_guide }}.

The static findings below are already reported and are listed so you do not repeat them. Judge one only if you are sure it is wrong.

Focus on what linters miss: unclear names, functions doing too many things, missing or misleading docstrings, magic numbers, deep nesting that early returns would flatten, non-idiomatic constructs, and inconsistent error handling.

Report at most 8 findings, the most valuable first. Use the category style or maintainability, and the severity low or info unless a readability problem hides a real risk of bugs.

Answer with this JSON:
{"static_judgements": [{"static_id": "S1", "verdict": "confirmed | false_positive | uncertain", "reason": "why", "adjusted_severity": "critical | high | medium | low | info | null"}],
 "findings": [{"start_line": 12, "end_line": 14, "category": "style", "severity": "low", "title": "at most 80 characters", "message": "what is wrong", "rationale": "why it matters", "evidence": "exact code copied from CODE", "cwe": null, "confidence": 0.7, "suggested_change": "one sentence, or null"}]}

{% include "_context.md" %}
