"""Error hierarchy for Margin.

Every error raised deliberately by the application derives from
:class:`MarginError`, so API handlers and pipeline stages can tell expected
failures apart from programming errors.
"""

from enum import StrEnum


class MarginError(Exception):
    """Base class for all errors raised by Margin."""


class InvalidScanIdError(MarginError):
    """A scan id is not in the format Margin generates, so it cannot name a scan."""


class IngestRejection(StrEnum):
    """Stable machine-readable reasons an upload was refused."""

    ARCHIVE_TOO_LARGE = "archive_too_large"
    CORRUPT_ARCHIVE = "corrupt_archive"
    COMPRESSION_RATIO = "compression_ratio"
    DUPLICATE_ENTRY = "duplicate_entry"
    ENCRYPTED_ENTRY = "encrypted_entry"
    INVALID_PATH = "invalid_path"
    PATH_TRAVERSAL = "path_traversal"
    SIZE_MISMATCH = "size_mismatch"
    SYMLINK = "symlink"
    TOO_MANY_FILES = "too_many_files"
    UNCOMPRESSED_TOO_LARGE = "uncompressed_too_large"


class IngestError(MarginError):
    """An upload was refused.

    Attributes:
        reason: Stable code for API clients and tests.
        message: Human-readable explanation that tells the user what to do.
    """

    def __init__(self, reason: IngestRejection, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class AnalyzerError(MarginError):
    """An analyzer could not produce results; the scan continues without them."""


class ToolUnavailableError(AnalyzerError):
    """The analyzer's executable is not installed, so the analyzer is skipped."""
