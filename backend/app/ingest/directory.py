"""Copy a local project's reviewable files into a scan workspace.

The CLI scans directories on the user's machine. Copying them through the same
filters and limits as uploads means analyzers see exactly what an uploaded
archive would give them: no dependencies or build output, and nothing reached
through a symbolic link. Paths matching the caller's exclude patterns are left
out as well, such as fixtures that contain vulnerable code on purpose.
"""

import os
import stat
from collections.abc import Sequence
from fnmatch import fnmatchcase
from functools import partial
from pathlib import Path, PurePosixPath

from app.errors import IngestError, IngestRejection
from app.ingest.filters import (
    BINARY_SNIFF_BYTES,
    EXCLUDED_DIRECTORIES,
    skip_reason_for_content,
    skip_reason_for_path,
)
from app.ingest.models import MB, IngestLimits, IngestResult, SkippedFile, SkipReason
from app.ingest.paths import safe_relative_path
from app.ingest.zipsafe import write_limited

_COPY_CHUNK_BYTES = 64 * 1024


def ingest_directory(
    source: Path, destination: Path, limits: IngestLimits, exclude: Sequence[str] = ()
) -> IngestResult:
    """Copy reviewable files from ``source`` into ``destination``.

    This is blocking I/O; call it with ``asyncio.to_thread`` from async code.

    Args:
        source: The project directory to scan.
        destination: The scan's empty source directory.
        limits: Size and count limits to enforce.
        exclude: Glob patterns for paths to leave out; see :func:`is_excluded`.

    Raises:
        IngestError: If the project has more reviewable files, or more bytes of
            them, than the limits allow.
    """
    root = source.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    skipped: list[SkippedFile] = []
    total_bytes = 0

    for directory, subdirectories, names in os.walk(root, followlinks=False):
        current = Path(directory)
        relative_directory = PurePosixPath(*current.relative_to(root).parts)
        subdirectories[:] = _descend_into(
            current, relative_directory, subdirectories, skipped, exclude
        )
        for name in sorted(names):
            path, relative = current / name, relative_directory / name
            if is_excluded(relative, exclude):
                skipped.append(SkippedFile(path=relative.as_posix(), reason=SkipReason.EXCLUDED))
                continue
            reason, size = _inspect(path, relative, limits)
            if reason is None:
                _enforce_limits(len(files) + 1, total_bytes + size, limits)
                reason = _copy(path, destination.joinpath(*relative.parts), size)
            if reason is not None:
                skipped.append(SkippedFile(path=relative.as_posix(), reason=reason))
                continue
            total_bytes += size
            files.append(relative.as_posix())

    return IngestResult(
        root=destination.resolve(),
        files=sorted(files),
        skipped=sorted(skipped, key=lambda item: item.path),
    )


def is_excluded(path: PurePosixPath, patterns: Sequence[str]) -> bool:
    """Whether a path relative to the project root matches an exclude pattern.

    Patterns are shell-style globs matched against the whole relative path, where
    ``*`` also matches ``/``: ``eval/datasets``, ``*/fixtures`` or ``*.generated.py``.
    A matching directory is left out with everything in it.
    """
    text = path.as_posix()
    return any(fnmatchcase(text, pattern.strip("/")) for pattern in patterns)


def _descend_into(
    current: Path,
    relative: PurePosixPath,
    subdirectories: list[str],
    skipped: list[SkippedFile],
    exclude: Sequence[str],
) -> list[str]:
    kept: list[str] = []
    for name in sorted(subdirectories):
        path = (relative / name).as_posix()
        if (current / name).is_symlink():
            skipped.append(SkippedFile(path=path, reason=SkipReason.SYMLINK))
        elif is_excluded(relative / name, exclude):
            skipped.append(SkippedFile(path=path, reason=SkipReason.EXCLUDED))
        elif name.lower() in EXCLUDED_DIRECTORIES:
            skipped.append(SkippedFile(path=path, reason=SkipReason.EXCLUDED_DIRECTORY))
        else:
            kept.append(name)
    return kept


def _inspect(
    path: Path, relative: PurePosixPath, limits: IngestLimits
) -> tuple[SkipReason | None, int]:
    """Why a directory entry is skipped, if it is, and its size.

    The entry type comes from one ``lstat`` before anything is opened, so named
    pipes and devices are never read (reading a pipe would block the scan).
    Files the user cannot read are skipped rather than failing the scan.
    """
    try:
        status = path.lstat()
    except OSError:
        return SkipReason.UNREADABLE, 0
    if stat.S_ISLNK(status.st_mode):
        return SkipReason.SYMLINK, 0
    if not stat.S_ISREG(status.st_mode):
        return SkipReason.SPECIAL_FILE, 0
    try:
        safe_relative_path(relative.as_posix(), limits.max_path_length)
    except IngestError:
        return SkipReason.INVALID_NAME, 0
    reason = skip_reason_for_path(relative)
    if reason is not None:
        return reason, 0
    try:
        with path.open("rb") as handle:
            head = handle.read(BINARY_SNIFF_BYTES)
    except OSError:
        return SkipReason.UNREADABLE, 0
    return skip_reason_for_content(status.st_size, head, limits.max_file_bytes), status.st_size


def _enforce_limits(file_count: int, total_bytes: int, limits: IngestLimits) -> None:
    if file_count > limits.max_files:
        raise IngestError(
            IngestRejection.TOO_MANY_FILES,
            f"The project has more than {limits.max_files:,} reviewable files. "
            "Scan a smaller directory.",
        )
    if total_bytes > limits.max_total_uncompressed_bytes:
        raise IngestError(
            IngestRejection.UNCOMPRESSED_TOO_LARGE,
            f"The project's reviewable files exceed "
            f"{limits.max_total_uncompressed_bytes // MB} MB. Scan a smaller directory.",
        )


def _copy(source: Path, target: Path, size: int) -> SkipReason | None:
    """Copy at most ``size`` bytes, so a file growing during the scan cannot exceed the limits.

    Returns:
        ``None`` when copied, or ``UNREADABLE`` if the file could not be read.
    """
    try:
        with source.open("rb") as handle:
            write_limited(iter(partial(handle.read, _COPY_CHUNK_BYTES), b""), target, size)
    except OSError:
        target.unlink(missing_ok=True)
        return SkipReason.UNREADABLE
    return None
