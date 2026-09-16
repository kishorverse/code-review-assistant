"""Validation of file names that come from archives and uploads.

A name becomes a relative path only if it cannot point outside the extraction
directory and is a valid file name on every platform the backend runs on, so a
scan behaves the same on Linux, macOS and Windows.
"""

from pathlib import PurePosixPath, PureWindowsPath

from app.errors import IngestError, IngestRejection

_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)
_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*') | frozenset(chr(code) for code in range(32))
_MAX_COMPONENT_LENGTH = 255
_MAX_DISPLAY_LENGTH = 80


def safe_relative_path(name: str, max_length: int) -> PurePosixPath:
    """Validate an archive member or uploaded file name and return it as a relative path.

    Backslashes count as separators because archives created on Windows may use
    them. Empty and ``.`` segments are dropped; anything that could resolve
    outside the destination directory is rejected.

    Args:
        name: The name exactly as it appears in the archive or upload.
        max_length: Longest accepted name, in characters.

    Raises:
        IngestError: If the name is absolute, climbs upwards with ``..``, or is
            not a portable file name.
    """
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or PureWindowsPath(normalized).drive:
        raise IngestError(
            IngestRejection.PATH_TRAVERSAL,
            f"The upload contains an absolute path ({quote_name(name)}). "
            "Archive the project folder itself, not absolute paths.",
        )

    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if ".." in parts:
        raise IngestError(
            IngestRejection.PATH_TRAVERSAL,
            f"The upload contains a path that points outside the project ({quote_name(name)}).",
        )
    if not parts or len(normalized) > max_length:
        raise IngestError(
            IngestRejection.INVALID_PATH,
            f"The upload contains an empty or overly long path ({quote_name(name)}).",
        )
    if not all(_is_portable_component(part) for part in parts):
        raise IngestError(
            IngestRejection.INVALID_PATH,
            f"The upload contains a file name that is not portable ({quote_name(name)}).",
        )
    return PurePosixPath(*parts)


def _is_portable_component(part: str) -> bool:
    stem = part.split(".", 1)[0].lower()
    return (
        len(part) <= _MAX_COMPONENT_LENGTH
        and not any(char in _FORBIDDEN_CHARACTERS for char in part)
        and not part.endswith((".", " "))
        and stem not in _WINDOWS_RESERVED_NAMES
    )


def quote_name(name: str) -> str:
    """Quote a name for an error message without echoing control characters."""
    shown = name if len(name) <= _MAX_DISPLAY_LENGTH else name[:_MAX_DISPLAY_LENGTH] + "…"
    return repr(shown)
