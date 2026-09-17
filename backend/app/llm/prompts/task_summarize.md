{# PROMPT_VERSION: 1 #}
TASK: Write the executive summary of this code review.

PROJECT:
{{ project }}

FINDINGS (most severe first):
{{ findings }}

Answer with this JSON:
{"headline": "one sentence overall assessment", "strengths": ["up to 3 short points"], "top_risks": [{"title": "short title", "files": ["path"], "why": "one sentence"}], "recommended_next_steps": ["up to 5 concrete actions, most important first"]}
