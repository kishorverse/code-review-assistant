{# PROMPT_VERSION: 1 #}
TASK: Review the code for correctness bugs, security vulnerabilities and performance problems.

Look especially for:
- Bugs: off-by-one errors, null or None dereferences, wrong comparisons, mutable default arguments, unhandled exceptions, resource leaks, missing await or blocking calls in async code, shadowed variables, unreachable branches, wrong return values.
- Security: injection (SQL, shell, template, path), unsafe deserialization, eval or exec on untrusted input, weak cryptography or randomness, hardcoded secrets, SSRF, missing input validation, insecure temporary files, exceptions swallowed in a way that hides failures. Give a CWE id when you are confident.
- Performance: quadratic loops over large collections, repeated work inside loops, string concatenation in loops, N+1 queries, reading whole files into memory unnecessarily, membership tests on lists that should use a set or dict.

Use the categories bug, security, performance, maintainability or typing.

Answer with this JSON:
{"static_judgements": [{"static_id": "S1", "verdict": "confirmed | false_positive | uncertain", "reason": "why", "adjusted_severity": "critical | high | medium | low | info | null"}],
 "findings": [{"start_line": 12, "end_line": 12, "category": "bug", "severity": "medium", "title": "at most 80 characters", "message": "what is wrong", "rationale": "why it matters", "evidence": "exact code copied from CODE", "cwe": "CWE-89 or null", "confidence": 0.8, "suggested_change": "one sentence, or null"}]}

EXAMPLE 1
CODE:
 7 | def average(values):
 8 |     return sum(values) / len(values)
Answer:
{"static_judgements": [], "findings": [{"start_line": 8, "end_line": 8, "category": "bug", "severity": "medium", "title": "Division by zero when values is empty", "message": "len(values) is 0 for an empty sequence, so the division raises ZeroDivisionError.", "rationale": "Any caller passing an empty collection crashes instead of getting a defined result.", "evidence": "return sum(values) / len(values)", "cwe": "CWE-369", "confidence": 0.8, "suggested_change": "Return 0 or raise a clear ValueError when values is empty."}]}

EXAMPLE 2
CODE:
 3 | def full_name(user):
 4 |     return " ".join(part for part in (user.first, user.last) if part)
Answer:
{"static_judgements": [], "findings": []}

Now review this code.

{% include "_context.md" %}
