"""Keep detected secrets out of everything Margin shows or sends.

detect-secrets reports each distinct secret once per file, identified by its
line and the SHA-1 of its value. The same value can appear on other lines
(a key pasted twice), and other tools report findings on the same lines, so a
line counts as sensitive when it was reported, or when any value on it hashes
to a reported secret. The index stores only line numbers and hashes, never the
secrets themselves.
"""

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.findings import REDACTED_EVIDENCE

_SEPARATORS = re.compile(r"""[\s'"`,;()\[\]{}<>=:@/\\]+""")
_QUOTED = re.compile(r"""(['"`])(.+?)\1""")


@dataclass
class SecretIndex:
    """Where secrets were detected, by file line and value hash."""

    reported_lines: dict[str, set[int]] = field(default_factory=dict)
    value_hashes: set[str] = field(default_factory=set)

    def mark_lines(self, file_path: str, lines: Iterable[int]) -> None:
        """Record lines a detector reported as containing a secret."""
        self.reported_lines.setdefault(file_path, set()).update(lines)

    def add_hashes(self, hashes: Iterable[str]) -> None:
        """Record SHA-1 hex digests of detected secret values."""
        self.value_hashes.update(hashes)

    def is_sensitive(self, file_path: str, line_number: int, text: str) -> bool:
        """Whether the line was reported or contains a value matching a detected secret."""
        if line_number in self.reported_lines.get(file_path, ()):
            return True
        if not self.value_hashes:
            return False
        return any(_sha1(value) in self.value_hashes for value in candidate_values(text))


def candidate_values(text: str) -> set[str]:
    """Substrings of a line that could be a secret value: words and quoted strings."""
    values = {part for part in _SEPARATORS.split(text) if part}
    values.update(match.group(2) for match in _QUOTED.finditer(text))
    values.update(word.strip("'\"`,;()") for word in text.split())
    values.discard("")
    return values


def redact_lines(
    file_path: str, first_line: int, lines: Sequence[str], index: SecretIndex
) -> list[str]:
    """Replace every sensitive line of an excerpt with the redaction marker."""
    return [
        REDACTED_EVIDENCE if index.is_sensitive(file_path, first_line + offset, line) else line
        for offset, line in enumerate(lines)
    ]


def _sha1(value: str) -> str:
    # detect-secrets identifies secrets by SHA-1; this is matching, not protection.
    return hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).hexdigest()
