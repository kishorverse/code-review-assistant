"""Copy a local project's reviewable files into a scan workspace.

The CLI scans directories on the user's machine. Copying them through the same
filters and limits as uploads means analyzers see exactly what an uploaded
archive would give them: no dependencies or build output, and nothing reached
through a symbolic link.
"""

import os
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


def ingest_directory(source: Path, destination: Path, limits: IngestLimits) -> IngestResult:
    """Copy reviewable files from ``source`` into ``destination``.

    This is blocking I/O; call it with ``asyncio.to_thread`` from async code.

    Args:
        source: The project directory to scan.
        destination: The scan's empty source directory.
        limits: Size and count limits to enforce.

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
        subdirectories[:] = _descend_into(current, relative_directory, subdirectories, skipped)
        for name in sorted(names):
            relative = relative_directory / name
            size = (current / name).lstat().st_size
            reason = _skip_reason(current / name, relative, size, limits)
            if reason is not None:
                skipped.append(SkippedFile(path=relative.as_posix(), reason=reason))
                continue
            total_bytes += size
            _enforce_limits(len(files) + 1, total_bytes, limits)
            _copy(current / name, destination.joinpath(*relative.parts), size)
            files.append(relative.as_posix())

    return IngestResult(
        root=destination.resolve(),
        files=sorted(files),
        skipped=sorted(skipped, key=lambda item: item.path),
    )


def _descend_into(
    current: Path, relative: PurePosixPath, subdirectories: list[str], skipped: list[SkippedFile]
) -> list[str]:
    kept: list[str] = []
    for name in sorted(subdirectories):
        path = (relative / name).as_posix()
        if (current / name).is_symlink():
            skipped.append(SkippedFile(path=path, reason=SkipReason.SYMLINK))
        elif name.lower() in EXCLUDED_DIRECTORIES:
            skipped.append(SkippedFile(path=path, reason=SkipReason.EXCLUDED_DIRECTORY))
        else:
            kept.append(name)
    return kept


def _skip_reason(
    path: Path, relative: PurePosixPath, size: int, limits: IngestLimits
) -> SkipReason | None:
    if path.is_symlink():
        return SkipReason.SYMLINK
    try:
        safe_relative_path(relative.as_posix(), limits.max_path_length)
    except IngestError:
        return SkipReason.INVALID_NAME
    reason = skip_reason_for_path(relative)
    if reason is not None:
        return reason
    with path.open("rb") as handle:
        head = handle.read(BINARY_SNIFF_BYTES)
    return skip_reason_for_content(size, head, limits.max_file_bytes)


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


def _copy(source: Path, target: Path, size: int) -> None:
    """Copy at most ``size`` bytes, so a file growing during the scan cannot exceed the limits."""
    with source.open("rb") as handle:
        write_limited(iter(partial(handle.read, _COPY_CHUNK_BYTES), b""), target, size)
