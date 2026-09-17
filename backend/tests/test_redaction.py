import hashlib

from app.findings import REDACTED_EVIDENCE
from app.redaction import SecretIndex, candidate_values, redact_lines

# Assembled at runtime so this repository never contains a secret-shaped literal.
KEY = "AKIA" + "IOSFODNN7" + "EXAMPLE"
KEY_HASH = hashlib.sha1(KEY.encode(), usedforsecurity=False).hexdigest()


def index_with_key() -> SecretIndex:
    index = SecretIndex()
    index.mark_lines("app/settings.py", [3])
    index.add_hashes([KEY_HASH])
    return index


def test_candidate_values_include_words_and_quoted_strings() -> None:
    values = candidate_values(f'URL = "https://admin:{KEY}@db.internal/app"  # "two words"')

    assert KEY in values
    assert "two words" in values
    assert "admin" in values


def test_reported_lines_are_sensitive_regardless_of_content() -> None:
    assert index_with_key().is_sensitive("app/settings.py", 3, "anything")
    assert not index_with_key().is_sensitive("app/other.py", 3, "anything")


def test_copies_of_a_detected_value_are_sensitive_on_any_line_and_file() -> None:
    index = index_with_key()

    assert index.is_sensitive("app/settings.py", 10, f"BACKUP_KEY = '{KEY}'")
    assert index.is_sensitive("deploy/env.sh", 1, f"export AWS_ACCESS_KEY_ID={KEY}")
    assert not index.is_sensitive("app/settings.py", 11, "TIMEOUT = 30")


def test_redact_lines_replaces_only_sensitive_lines() -> None:
    lines = ["import os", "", "AWS_KEY = os.environ['X']", f"KEY_COPY = '{KEY}'"]

    redacted = redact_lines("app/settings.py", 1, lines, index_with_key())

    assert redacted == ["import os", "", REDACTED_EVIDENCE, REDACTED_EVIDENCE]
