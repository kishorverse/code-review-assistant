{# PROMPT_VERSION: 1 #}
TASK: Another reviewer reported the issue below. Decide independently whether it is real. Many reported issues are false positives.

File: {{ file_path }} ({{ language }})

REPORTED_ISSUE:
{{ issue }}

CODE:
{{ code }}

Answer with this JSON:
{"verdict": "valid | invalid | uncertain", "reason": "1 to 3 sentences grounded in the code", "corrected_severity": "critical | high | medium | low | info | null", "confidence": 0.8}
