"""Combine static findings, models' judgements of them and new AI findings.

Rules, in order of precedence:

- A confirmation outweighs a dismissal: if any model confirms a static finding,
  it stays open, the model is added to its sources, and its confidence rises to
  at least 0.8, since two independent sources now agree.
- A dismissed finding is kept, labelled "dismissed by AI" with the model's
  reason.
- A high or critical security finding is protected: a model alone can neither
  dismiss it (it is marked as needing human review instead) nor lower its
  severity (the suggestion is only noted). An instruction hidden in the code
  therefore cannot make a real vulnerability disappear.
- An AI finding that repeats an existing finding (same file and category,
  overlapping lines) is merged into it rather than listed twice.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence

from app.findings import Category, Finding, FindingStatus, Severity
from app.llm.config import PROVIDER_NAMES
from app.review.answers import JudgementVerdict
from app.review.reviewer import Judged

REPORTED_STATUSES = frozenset({FindingStatus.OPEN, FindingStatus.NEEDS_REVIEW})
CONFIRMED_CONFIDENCE = 0.8


def is_ai_only(finding: Finding) -> bool:
    """Whether only models, and no deterministic tool, reported a finding."""
    return all(source in PROVIDER_NAMES for source in finding.sources)


def is_unconfident(finding: Finding, min_confidence: float) -> bool:
    """Whether an AI-only finding falls below the confidence threshold.

    The threshold never hides deterministic findings: a tool's own confidence rating
    (Bandit rates some real injections as low confidence) is not a reason to hide them.
    """
    return is_ai_only(finding) and finding.confidence < min_confidence


def is_reported(finding: Finding, min_confidence: float) -> bool:
    """Whether a finding belongs in the default report: open or needing review, and not an
    AI-only finding below the confidence threshold."""
    return finding.status in REPORTED_STATUSES and not is_unconfident(finding, min_confidence)


def apply_judgements(findings: Sequence[Finding], judged: Iterable[Judged]) -> list[Finding]:
    """Update findings according to the models' judgements, keeping their order."""
    by_id: dict[str, list[Judged]] = defaultdict(list)
    for entry in judged:
        by_id[entry.finding.id].append(entry)
    return [
        judge(finding, by_id[finding.id]) if finding.id in by_id else finding
        for finding in findings
    ]


def judge(finding: Finding, judged: Sequence[Judged]) -> Finding:
    """Apply one or more judgements of the same finding."""
    confirmed = [e for e in judged if e.judgement.verdict is JudgementVerdict.CONFIRMED]
    if confirmed:
        return _confirm(finding, confirmed)
    dismissed = [e for e in judged if e.judgement.verdict is JudgementVerdict.FALSE_POSITIVE]
    if dismissed:
        return _dismiss(finding, dismissed[0])
    first = judged[0]
    if not first.judgement.reason:
        return finding
    return finding.model_copy(
        update={"ai_note": _note(f"{first.provider} could not confirm or rule this out", first)}
    )


def merge_ai_findings(findings: Sequence[Finding], new: Iterable[Finding]) -> list[Finding]:
    """Add AI findings, merging each into an existing finding for the same issue."""
    merged = list(findings)
    for finding in new:
        index = next(
            (i for i, existing in enumerate(merged) if _same_issue(existing, finding)), None
        )
        if index is None:
            merged.append(finding)
        else:
            merged[index] = _combine(merged[index], finding)
    return merged


def is_protected(finding: Finding) -> bool:
    """Whether a finding is too serious for a model alone to dismiss or downgrade."""
    return finding.category is Category.SECURITY and finding.severity.rank >= Severity.HIGH.rank


def _confirm(finding: Finding, confirmed: Sequence[Judged]) -> Finding:
    first = confirmed[0]
    update: dict[str, object] = {
        "sources": _union(finding.sources, [entry.provider for entry in confirmed]),
        "rationale": finding.rationale or first.judgement.reason or None,
        "confidence": max(finding.confidence, CONFIRMED_CONFIDENCE),
    }
    adjusted = first.judgement.adjusted_severity
    if adjusted is None or adjusted is finding.severity:
        return finding.model_copy(update=update)
    change = f"from {finding.severity.value} to {adjusted.value}"
    if adjusted.rank < finding.severity.rank and is_protected(finding):
        update["ai_note"] = _note(
            f"{first.provider} suggested lowering the severity {change}", first
        )
    else:
        update["severity"] = adjusted
        update["ai_note"] = _note(f"{first.provider} changed the severity {change}", first)
    return finding.model_copy(update=update)


def _dismiss(finding: Finding, first: Judged) -> Finding:
    status = FindingStatus.NEEDS_REVIEW if is_protected(finding) else FindingStatus.DISMISSED_BY_AI
    note = _note(f"{first.provider} considers this a false positive", first)
    return finding.model_copy(update={"status": status, "ai_note": note})


def _same_issue(existing: Finding, new: Finding) -> bool:
    return (
        existing.file_path == new.file_path
        and existing.category is new.category
        and existing.start_line <= new.end_line
        and new.start_line <= existing.end_line
    )


def _combine(existing: Finding, new: Finding) -> Finding:
    update: dict[str, object] = {
        "sources": _union(existing.sources, new.sources),
        "confidence": max(existing.confidence, new.confidence),
        "rationale": existing.rationale or new.rationale,
        "suggestion": existing.suggestion or new.suggestion,
        "cwe": existing.cwe or new.cwe,
    }
    if is_ai_only(existing) and new.severity.rank > existing.severity.rank:
        update["severity"] = new.severity
    if existing.status is FindingStatus.DISMISSED_BY_AI:
        update["status"] = FindingStatus.NEEDS_REVIEW
        reporters = ", ".join(new.sources)
        update["ai_note"] = f"{existing.ai_note} {reporters} reported it as an issue."
    return existing.model_copy(update=update)


def _note(summary: str, entry: Judged) -> str:
    reason = entry.judgement.reason
    return f"{summary}: {reason}" if reason else f"{summary}."


def _union(first: Sequence[str], second: Iterable[str]) -> list[str]:
    return list(dict.fromkeys([*first, *second]))
