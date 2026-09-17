"""Error hierarchy for Margin.

Every error raised deliberately by the application derives from
:class:`MarginError`, so API handlers and pipeline stages can tell expected
failures apart from programming errors.
"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.models import CallRecord, Task


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


class ProviderError(MarginError):
    """An LLM provider call failed. The router decides whether to try another provider."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class RateLimitedError(ProviderError):
    """The provider asked us to slow down (HTTP 429).

    Attributes:
        retry_after: Seconds the provider asked us to wait, when it said.
    """

    def __init__(self, provider: str, message: str, retry_after: float | None = None) -> None:
        super().__init__(provider, message)
        self.retry_after = retry_after


class QuotaExhaustedError(ProviderError):
    """A daily or monthly allowance is used up; retrying before it resets is pointless.

    Attributes:
        resets_at: When the allowance renews, if known.
    """

    def __init__(self, provider: str, message: str, resets_at: datetime | None = None) -> None:
        super().__init__(provider, message)
        self.resets_at = resets_at


class ProviderAuthError(ProviderError):
    """The API key was rejected; the provider stays unusable until configuration changes."""


class ProviderConfigError(ProviderError):
    """The model id or endpoint URL is wrong; the provider stays unusable until it is fixed."""


class ProviderUnavailableError(ProviderError):
    """A provider-wide failure: a timeout, a connection or server error, or a garbled response."""


class ProviderRequestError(ProviderError):
    """The provider is working but could not answer this particular request.

    Examples are a request it rejects as invalid, a blocked prompt, or an answer
    cut off at the output token limit. Other requests may still succeed.
    """


class AllProvidersUnavailableError(MarginError):
    """No provider could complete a request; the caller falls back to static results only.

    Attributes:
        task: The task that could not be completed.
        attempts: What happened with each provider that was considered.
    """

    def __init__(self, task: "Task", attempts: "Sequence[CallRecord]") -> None:
        tried = ", ".join(f"{record.provider}: {record.status}" for record in attempts)
        super().__init__(f"no provider could complete the {task} task ({tried or 'none enabled'})")
        self.task = task
        self.attempts = list(attempts)


class ConfigError(MarginError):
    """A configuration file is missing or invalid."""
