"""Check that an issue a model reported is anchored in the code it was shown.

This is the first guard against hallucinated findings. A reported issue is
kept only if it cites lines the model actually saw and its quoted evidence
appears at those lines. Evidence is compared with whitespace collapsed and
line-number prefixes removed, and may come from up to two lines around the
cited range, because models are often a line off.
"""

import re

from app.preprocess.models import Chunk
from app.review.answers import ReportedIssue
from app.review.context import SourceText
from app.static.evidence import MAX_EVIDENCE_LINES

EVIDENCE_PADDING_LINES = 2
MIN_EVIDENCE_CHARACTERS = 3

_LINE_PREFIX = re.compile(r"^\s*\d+\s*\|\s?")


def ungrounded_reason(issue: ReportedIssue, chunk: Chunk, source: SourceText) -> str | None:
    """Why a reported issue is not anchored in the code, or ``None`` if it is."""
    if issue.end_line > len(source.lines):
        return "cites lines past the end of the file"
    shown = [*chunk.context, chunk.lines]
    if not all(
        any(r.start <= line <= r.end for r in shown) for line in (issue.start_line, issue.end_line)
    ):
        return "cites lines that were not shown"
    quoted = [_collapse(line) for line in clean_evidence(issue.evidence).splitlines()]
    quoted = [line for line in quoted if line]
    if sum(len(line) for line in quoted) < MIN_EVIDENCE_CHARACTERS:
        return "quotes no meaningful evidence"
    first = max(0, issue.start_line - 1 - EVIDENCE_PADDING_LINES)
    window = _collapse(" ".join(source.lines[first : issue.end_line + EVIDENCE_PADDING_LINES]))
    if not all(line in window for line in quoted):
        return "quotes code that is not at the cited lines"
    return None


def clean_evidence(evidence: str) -> str:
    """Evidence without line-number prefixes, trimmed to the length findings show."""
    lines = [_LINE_PREFIX.sub("", line).rstrip() for line in evidence.strip("\n").splitlines()]
    return "\n".join(lines[:MAX_EVIDENCE_LINES]).strip()


def _collapse(text: str) -> str:
    return " ".join(text.split())
