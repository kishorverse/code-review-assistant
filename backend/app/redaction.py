"""Keep detected secrets out of everything Margin shows or sends.

detect-secrets reports each distinct secret once per file, identified by its
line and the SHA-1 of its value. The same value can appear on other lines
(a key pasted twice), and other tools report findings on the same lines, so a
line counts as sensitive when it was reported, or when any value on it hashes
to a reported secret. The index stores only line numbers and hashes, never the
secrets themselves.

Evidence shown to people replaces a sensitive line entirely. Code sent to a
model keeps its shape instead: secrets become numbered placeholders, so the
model can still review the surrounding code and report the hardcoded secret.
"""

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.findings import REDACTED_EVIDENCE

_SEPARATORS = re.compile(r"""[\s'"`,;()\[\]{}<>=:@/\\]+""")
_QUOTED = re.compile(r"""(['"`])(.+?)\1""")
_KEY_BLOCK_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_KEY_BLOCK_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
MAX_KEY_BLOCK_LINES = 200
"""Masking stops here if a key block never ends, so a stray header cannot hide a whole file."""
REDACTED_VALUE = "<REDACTED_SECRET>"


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
        return bool(self.matching_values(text))

    def matching_values(self, text: str) -> set[str]:
        """Substrings of ``text`` whose hash matches a detected secret."""
        if not self.value_hashes:
            return set()
        return {value for value in candidate_values(text) if _sha1(value) in self.value_hashes}


class SecretMasker:
    """Replaces secrets in one file's lines with ``<REDACTED_SECRET_n>`` placeholders.

    - A value matching a detected secret is replaced wherever it appears.
    - On a reported line without such a value, string literals are replaced, or
      the whole line when it has none.
    - The body of a private key block is replaced line by line, because detectors
      report only the line where the block begins.

    A value keeps one placeholder number throughout the file, so a model can still
    see that two lines use the same credential.
    """

    def __init__(self, file_path: str, index: SecretIndex) -> None:
        self._file_path = file_path
        self._index = index
        self._placeholders: dict[str, str] = {}

    def mask_lines(self, lines: Sequence[str]) -> list[str]:
        """Mask a whole file, given as its lines in order starting at line 1."""
        masked: list[str] = []
        key_block_lines = 0
        for number, line in enumerate(lines, start=1):
            begins, ends = _KEY_BLOCK_BEGIN.search(line), _KEY_BLOCK_END.search(line)
            if key_block_lines and not ends and key_block_lines <= MAX_KEY_BLOCK_LINES:
                masked.append(self._mask_whole_line(line))
                key_block_lines += 1
                continue
            key_block_lines = 1 if begins and not ends else 0
            if begins and ends:
                masked.append(self._mask_literals(line))
            else:
                masked.append(self._mask_line(number, line))
        return masked

    def mask_text(self, text: str) -> str:
        """Mask detected secret values in free text about this file, such as a tool's message.

        Placeholders match the ones used in the file's lines.
        """
        for value in sorted(self._index.matching_values(text), key=len, reverse=True):
            text = text.replace(value, self._placeholder(value))
        return text

    def _mask_line(self, number: int, line: str) -> str:
        if not self._index.is_sensitive(self._file_path, number, line):
            return line
        values = sorted(self._index.matching_values(line), key=len, reverse=True)
        if not values:
            return self._mask_literals(line)
        for value in values:
            line = line.replace(value, self._placeholder(value))
        return line

    def _mask_literals(self, line: str) -> str:
        if not _QUOTED.search(line):
            return self._mask_whole_line(line)
        return _QUOTED.sub(
            lambda match: f"{match.group(1)}{self._placeholder(match.group(2))}{match.group(1)}",
            line,
        )

    def _mask_whole_line(self, line: str) -> str:
        indentation = line[: len(line) - len(line.lstrip())]
        return f"{indentation}{self._placeholder(line.strip())}"

    def _placeholder(self, value: str) -> str:
        if value not in self._placeholders:
            self._placeholders[value] = f"<REDACTED_SECRET_{len(self._placeholders) + 1}>"
        return self._placeholders[value]


def candidate_values(text: str) -> set[str]:
    """Substrings of a line that could be a secret value: words and quoted strings."""
    values = {part for part in _SEPARATORS.split(text) if part}
    values.update(match.group(2) for match in _QUOTED.finditer(text))
    values.update(word.strip("'\"`,;()") for word in text.split())
    values.discard("")
    return values


def mask_secret_values(text: str, index: SecretIndex) -> str:
    """Replace detected secret values in free text that is not tied to one file."""
    for value in sorted(index.matching_values(text), key=len, reverse=True):
        text = text.replace(value, REDACTED_VALUE)
    return text


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
