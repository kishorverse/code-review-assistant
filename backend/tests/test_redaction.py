import hashlib

from app.findings import REDACTED_EVIDENCE
from app.redaction import (
    SecretIndex,
    SecretMasker,
    candidate_values,
    mask_secret_values,
    redact_lines,
)

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


# Built at runtime for the same reason as KEY.
BEGIN_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"
END_KEY = "-----END " + "RSA PRIVATE KEY-----"
OTHER_VALUE = "wJalrXUtnFEMI" + "K7MDENGbPxRfiCY"


def test_masker_replaces_detected_values_and_keeps_the_code_shape() -> None:
    lines = [f'AWS_KEY = "{KEY}"', "TIMEOUT = 30", f"backup = {{'key': '{KEY}'}}"]

    masked = SecretMasker("app/settings.py", index_with_key()).mask_lines(lines)

    assert masked == [
        'AWS_KEY = "<REDACTED_SECRET_1>"',
        "TIMEOUT = 30",
        "backup = {'key': '<REDACTED_SECRET_1>'}",
    ]


def test_masker_numbers_distinct_secrets_separately() -> None:
    index = SecretIndex()
    index.add_hashes(
        [KEY_HASH, hashlib.sha1(OTHER_VALUE.encode(), usedforsecurity=False).hexdigest()]
    )

    masked = SecretMasker("a.py", index).mask_lines(
        [f"A = '{KEY}'", f"B = '{OTHER_VALUE}'", f"C = '{KEY}'"]
    )

    assert masked == [
        "A = '<REDACTED_SECRET_1>'",
        "B = '<REDACTED_SECRET_2>'",
        "C = '<REDACTED_SECRET_1>'",
    ]


def test_masker_hides_literals_or_the_whole_line_on_reported_lines() -> None:
    index = SecretIndex()
    index.mark_lines("app/db.py", [1, 2])
    lines = ['connect(user="admin", password="not-in-any-hash")', "    token = build()", "x = 1"]

    masked = SecretMasker("app/db.py", index).mask_lines(lines)

    assert masked == [
        'connect(user="<REDACTED_SECRET_1>", password="<REDACTED_SECRET_2>")',
        "    <REDACTED_SECRET_3>",
        "x = 1",
    ]
    assert "not-in-any-hash" not in "\n".join(masked)


def test_masker_hides_the_body_of_private_key_blocks() -> None:
    body = ["MIIEowIBAAKCAQEA" + "0Z3VS5JJcds3xfn", "/ygWyF8PbnGy0AH" + "B7MhgHcTz6sE2I2y"]
    lines = ['PEM = """', BEGIN_KEY, *body, END_KEY, '"""', "print(PEM)"]

    masked = SecretMasker("keys.py", SecretIndex()).mask_lines(lines)

    assert masked[:2] == ['PEM = """', BEGIN_KEY]
    assert masked[2:4] == ["<REDACTED_SECRET_1>", "<REDACTED_SECRET_2>"]
    assert masked[4:] == [END_KEY, '"""', "print(PEM)"]


def test_masker_hides_a_private_key_written_on_one_line() -> None:
    line = f'PEM = "{BEGIN_KEY}\\nMIIEowIBAAKCAQEA\\n{END_KEY}"'

    [masked] = SecretMasker("keys.py", SecretIndex()).mask_lines([line])

    assert masked == 'PEM = "<REDACTED_SECRET_1>"'


def test_an_unterminated_key_block_does_not_hide_the_rest_of_the_file() -> None:
    lines = [BEGIN_KEY, *(["AAAA"] * 250), "def important(): pass"]

    masked = SecretMasker("notes.py", SecretIndex()).mask_lines(lines)

    assert masked[-1] == "def important(): pass"
    assert masked[1] == "<REDACTED_SECRET_1>"


def test_masker_masks_secret_values_in_free_text_with_the_files_placeholders() -> None:
    masker = SecretMasker("app/settings.py", index_with_key())
    masker.mask_lines([f'AWS_KEY = "{KEY}"'])

    assert (
        masker.mask_text(f"Literal['{KEY}'] is not str")
        == "Literal['<REDACTED_SECRET_1>'] is not str"
    )


def test_mask_secret_values_uses_a_generic_placeholder() -> None:
    assert (
        mask_secret_values(f"Unused value {KEY}", index_with_key())
        == "Unused value <REDACTED_SECRET>"
    )
    assert mask_secret_values("Nothing secret", index_with_key()) == "Nothing secret"
