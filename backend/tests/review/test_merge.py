import pytest

from app.findings import Category, Finding, FindingStatus, Severity
from app.review.answers import StaticJudgement
from app.review.merge import (
    apply_judgements,
    is_ai_only,
    is_protected,
    is_reported,
    merge_ai_findings,
)
from app.review.reviewer import Judged
from tests.review.conftest import make_finding

SQL = make_finding(severity=Severity.MEDIUM)
SHELL = make_finding(start_line=20, severity=Severity.HIGH, rule_id="B602", title="Shell injection")


def judged(finding: Finding, verdict: str, provider: str = "nvidia", **extra: object) -> Judged:
    judgement = StaticJudgement.model_validate(
        {"static_id": "S1", "verdict": verdict, "reason": "Because.", **extra}
    )
    return Judged(finding=finding, judgement=judgement, provider=provider)


def test_confirmation_adds_the_model_as_a_source_and_keeps_order() -> None:
    other = make_finding(start_line=30, rule_id="B105")

    updated = apply_judgements([SQL, other], [judged(SQL, "confirmed")])

    assert updated[0].sources == ["bandit", "nvidia"]
    assert updated[0].rationale == "Because."
    assert updated[0].status is FindingStatus.OPEN
    assert updated[1] is other


def test_dismissal_keeps_the_finding_with_the_models_reason() -> None:
    [dismissed] = apply_judgements([SQL], [judged(SQL, "false_positive")])

    assert dismissed.status is FindingStatus.DISMISSED_BY_AI
    assert dismissed.ai_note == "nvidia considers this a false positive: Because."
    assert dismissed.sources == ["bandit"]


def test_confirmation_outweighs_dismissal() -> None:
    [kept] = apply_judgements(
        [SQL], [judged(SQL, "false_positive", "hf-small"), judged(SQL, "confirmed", "nvidia")]
    )

    assert kept.status is FindingStatus.OPEN
    assert kept.sources == ["bandit", "nvidia"]


def test_serious_security_findings_cannot_be_dismissed_or_downgraded_by_a_model() -> None:
    [dismissal] = apply_judgements([SHELL], [judged(SHELL, "false_positive")])
    [downgrade] = apply_judgements([SHELL], [judged(SHELL, "confirmed", adjusted_severity="low")])

    assert is_protected(SHELL)
    assert dismissal.status is FindingStatus.NEEDS_REVIEW
    assert downgrade.severity is Severity.HIGH
    assert downgrade.ai_note == "nvidia suggested lowering the severity from high to low: Because."


def test_models_can_adjust_the_severity_of_other_findings() -> None:
    [raised] = apply_judgements([SQL], [judged(SQL, "confirmed", adjusted_severity="critical")])
    [lowered] = apply_judgements([SQL], [judged(SQL, "confirmed", adjusted_severity="low")])

    assert raised.severity is Severity.CRITICAL
    assert lowered.severity is Severity.LOW
    assert lowered.ai_note == "nvidia changed the severity from medium to low: Because."


def test_uncertain_judgements_add_a_note_only_when_there_is_a_reason() -> None:
    [noted] = apply_judgements([SQL], [judged(SQL, "uncertain")])
    [silent] = apply_judgements([SQL], [judged(SQL, "uncertain", reason="")])

    assert noted.ai_note == "nvidia could not confirm or rule this out: Because."
    assert noted.status is FindingStatus.OPEN
    assert silent is SQL


def ai_finding(**overrides: object) -> Finding:
    values: dict[str, object] = {
        "rule_id": "ai/security",
        "sources": ["gemini"],
        "confidence": 0.8,
        "rationale": "Attackers control name.",
        "suggestion": "Use parameters.",
        "cwe": "CWE-89",
    }
    return make_finding(**(values | overrides))


def test_an_ai_finding_for_an_existing_issue_is_merged_into_it() -> None:
    [merged] = merge_ai_findings([SQL], [ai_finding(start_line=4, end_line=5)])

    assert merged.id == SQL.id
    assert merged.sources == ["bandit", "gemini"]
    assert (merged.rationale, merged.suggestion, merged.cwe) == (
        "Attackers control name.",
        "Use parameters.",
        "CWE-89",
    )
    assert merged.severity is Severity.MEDIUM


def test_distinct_issues_are_added() -> None:
    elsewhere = ai_finding(start_line=40)
    other_kind = ai_finding(category=Category.PERFORMANCE)

    merged = merge_ai_findings([SQL], [elsewhere, other_kind])

    assert merged == [SQL, elsewhere, other_kind]


def test_ai_findings_for_the_same_issue_combine_sources_and_the_higher_severity() -> None:
    first = ai_finding(severity=Severity.MEDIUM, sources=["nvidia"])
    second = ai_finding(severity=Severity.HIGH, sources=["hf-large"], confidence=0.9)

    [merged] = merge_ai_findings([], [first, second])

    assert merged.sources == ["nvidia", "hf-large"]
    assert (merged.severity, merged.confidence) == (Severity.HIGH, 0.9)


def test_a_dismissed_finding_another_model_reports_needs_review() -> None:
    [dismissed] = apply_judgements([SQL], [judged(SQL, "false_positive")])

    [merged] = merge_ai_findings([dismissed], [ai_finding()])

    assert merged.status is FindingStatus.NEEDS_REVIEW
    assert merged.ai_note is not None
    assert merged.ai_note.endswith("gemini reported it as an issue.")


@pytest.mark.parametrize(
    ("overrides", "reported"),
    [
        ({}, True),
        ({"status": FindingStatus.NEEDS_REVIEW}, True),
        ({"status": FindingStatus.DISMISSED_BY_AI}, False),
        ({"confidence": 0.59}, False),
    ],
)
def test_is_reported(overrides: dict[str, object], reported: bool) -> None:
    assert is_reported(make_finding(**overrides), min_confidence=0.6) is reported


def test_is_ai_only() -> None:
    assert is_ai_only(ai_finding(sources=["nvidia", "gemini"]))
    assert not is_ai_only(ai_finding(sources=["bandit", "gemini"]))
