"""Single entry point that turns an uploaded file into a scan's source directory.

A ``.zip`` upload goes through safe archive extraction; any other upload is a
single source file. Both paths apply the same filters and return the same
:class:`~app.ingest.models.IngestResult`, so the pipeline never needs to know
which kind of upload it received.
"""

from functools import partial
from itertools import chain
from pathlib import Path

from app.ingest.filters import BINARY_SNIFF_BYTES, skip_reason_for_content, skip_reason_for_path
from app.ingest.models import IngestLimits, IngestResult, SkippedFile
from app.ingest.paths import safe_relative_path
from app.ingest.zipsafe import extract_archive, write_limited

ARCHIVE_SUFFIX = ".zip"
_COPY_CHUNK_BYTES = 64 * 1024


def ingest_upload(
    upload: Path, filename: str, destination: Path, limits: IngestLimits
) -> IngestResult:
    """Extract an uploaded archive or copy a single uploaded file into ``destination``.

    This is blocking I/O; call it with ``asyncio.to_thread`` from async code.

    Args:
        upload: Where the uploaded bytes were saved.
        filename: The name the client sent. For a single file only its final
            component is used, because clients may send a full local path.
        destination: The scan's source directory.
        limits: Size and count limits to enforce.

    Raises:
        IngestError: If the file name or the archive is unsafe or unreadable.
    """
    if filename.lower().endswith(ARCHIVE_SUFFIX):
        return extract_archive(upload, destination, limits)
    return _ingest_single_file(upload, filename, destination, limits)


def _ingest_single_file(
    upload: Path, filename: str, destination: Path, limits: IngestLimits
) -> IngestResult:
    base_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    relative = safe_relative_path(base_name, limits.max_path_length)
    name = relative.as_posix()
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    size = upload.stat().st_size

    with upload.open("rb") as source:
        head = source.read(BINARY_SNIFF_BYTES)
        reason = skip_reason_for_path(relative) or skip_reason_for_content(
            size, head, limits.max_file_bytes
        )
        if reason is not None:
            skipped = [SkippedFile(path=name, reason=reason)]
            return IngestResult(root=root, files=[], skipped=skipped)
        remaining = iter(partial(source.read, _COPY_CHUNK_BYTES), b"")
        write_limited(chain((head,), remaining), root / name, size)

    return IngestResult(root=root, files=[name], skipped=[])
