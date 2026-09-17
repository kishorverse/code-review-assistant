"""Attach the offending source lines to findings.

Evidence lets reviewers, the LLM verifier and reports see the code without
opening the file. Findings that already carry evidence (including redacted
secrets) are left untouched, and lines holding a detected secret are masked.
"""

from collections import defaultdict
from pathlib import Path, PurePosixPath

from app.findings import Finding
from app.redaction import SecretIndex, redact_lines

MAX_EVIDENCE_LINES = 5


def attach_evidence(
    findings: list[Finding], root: Path, secrets: SecretIndex | None = None
) -> list[Finding]:
    """Return findings with evidence filled from their files, in the same order.

    Lines that contain a detected secret are replaced with the redaction marker,
    whichever tool's finding they belong to. Each file is read once. This is
    blocking I/O; call it with ``asyncio.to_thread`` from async code.
    """
    secrets = secrets or SecretIndex()
    needed: dict[str, list[int]] = defaultdict(list)
    for index, finding in enumerate(findings):
        if finding.evidence is None:
            needed[finding.file_path].append(index)

    completed = list(findings)
    for file_path, indexes in needed.items():
        lines = _read_lines(root, file_path)
        for index in indexes:
            finding = completed[index]
            last = min(finding.end_line, finding.start_line + MAX_EVIDENCE_LINES - 1)
            excerpt_lines = [line.rstrip() for line in lines[finding.start_line - 1 : last]]
            excerpt = "\n".join(redact_lines(file_path, finding.start_line, excerpt_lines, secrets))
            if excerpt.strip():
                completed[index] = finding.model_copy(update={"evidence": excerpt})
    return completed


def _read_lines(root: Path, file_path: str) -> list[str]:
    path = root.joinpath(*PurePosixPath(file_path).parts)
    try:
        return path.read_bytes().decode("utf-8-sig", errors="replace").split("\n")
    except OSError:
        return []
