"""Safe extraction of uploaded zip archives.

The archive is validated as a whole before anything is written: member names
(zip slip), symbolic links, encryption, duplicates, member count, declared
sizes and compression ratio (zip bombs). Each member is then streamed to disk
with a byte limit, so an archive that lies about its sizes is caught too.
If extraction fails part-way, the destination directory is emptied again.

Extraction is blocking I/O; call it with ``asyncio.to_thread`` from async code.
"""

import lzma
import shutil
import stat
import zipfile
import zlib
from collections.abc import Iterable, Iterator
from itertools import chain
from pathlib import Path, PurePosixPath
from typing import IO, NamedTuple

from app.errors import IngestError, IngestRejection
from app.ingest.filters import BINARY_SNIFF_BYTES, skip_reason_for_content, skip_reason_for_path
from app.ingest.models import MB, IngestLimits, IngestResult, SkippedFile
from app.ingest.paths import quote_name, safe_relative_path

_COPY_CHUNK_BYTES = 64 * 1024
_ENCRYPTED_FLAG = 0x1
_CORRUPT_DATA_ERRORS = (
    zipfile.BadZipFile,
    zlib.error,
    lzma.LZMAError,
    EOFError,
    NotImplementedError,
)


class _Member(NamedTuple):
    info: zipfile.ZipInfo
    path: PurePosixPath


def extract_archive(archive: Path, destination: Path, limits: IngestLimits) -> IngestResult:
    """Validate a zip archive and extract its reviewable files.

    Args:
        archive: The uploaded ``.zip`` file.
        destination: Directory to extract into; created if missing. It should be empty.
        limits: Size and count limits to enforce.

    Returns:
        The extracted files and the files that were skipped, with reasons.

    Raises:
        IngestError: If the archive is unreadable or unsafe. ``destination`` is
            left empty in that case.
    """
    archive_size = archive.stat().st_size
    if archive_size > limits.max_archive_bytes:
        raise IngestError(
            IngestRejection.ARCHIVE_TOO_LARGE,
            f"The archive is larger than {limits.max_archive_bytes // MB} MB. "
            "Remove build folders or dependencies and try again.",
        )

    try:
        with zipfile.ZipFile(archive) as zip_file:
            members = _validate_members(zip_file.infolist(), archive_size, limits)
            return _extract_members(zip_file, members, destination, limits)
    except _CORRUPT_DATA_ERRORS as error:
        _clear_directory(destination)
        raise _corrupt_archive_error() from error
    except BaseException:
        _clear_directory(destination)
        raise


def _corrupt_archive_error() -> IngestError:
    return IngestError(
        IngestRejection.CORRUPT_ARCHIVE,
        "The file could not be read as a zip archive. "
        "It may be corrupt or use an unsupported compression method.",
    )


def _validate_members(
    infos: list[zipfile.ZipInfo], archive_size: int, limits: IngestLimits
) -> list[_Member]:
    members: list[_Member] = []
    seen: set[str] = set()
    total_uncompressed = 0

    for info in infos:
        path = safe_relative_path(info.filename, limits.max_path_length)
        _reject_special_entry(info)
        key = path.as_posix().casefold()
        if key in seen:
            raise IngestError(
                IngestRejection.DUPLICATE_ENTRY,
                f"The archive contains the same path more than once ({quote_name(info.filename)}).",
            )
        seen.add(key)
        # ZipInfo.is_dir() only recognizes "/", but Windows tools may write "src\" entries.
        if info.filename.endswith(("/", "\\")):
            continue

        members.append(_Member(info, path))
        total_uncompressed += info.file_size
        if len(members) > limits.max_files:
            raise IngestError(
                IngestRejection.TOO_MANY_FILES,
                f"The archive contains more than {limits.max_files:,} files. "
                "Remove dependencies or generated files and try again.",
            )

    _reject_file_used_as_directory(members)
    _reject_oversized_expansion(total_uncompressed, archive_size, limits)
    return members


def _reject_special_entry(info: zipfile.ZipInfo) -> None:
    if stat.S_ISLNK(info.external_attr >> 16):
        raise IngestError(
            IngestRejection.SYMLINK,
            f"The archive contains a symbolic link ({quote_name(info.filename)}). "
            "Links are not allowed because they can point outside the project.",
        )
    if info.flag_bits & _ENCRYPTED_FLAG:
        raise IngestError(
            IngestRejection.ENCRYPTED_ENTRY,
            "The archive contains password-protected files. Upload an unencrypted archive.",
        )


def _reject_file_used_as_directory(members: list[_Member]) -> None:
    file_keys = {member.path.as_posix().casefold() for member in members}
    for member in members:
        for parent in member.path.parents:
            if parent.as_posix().casefold() in file_keys:
                raise IngestError(
                    IngestRejection.DUPLICATE_ENTRY,
                    f"The archive uses {quote_name(parent.as_posix())} "
                    "as both a file and a folder.",
                )


def _reject_oversized_expansion(
    total_uncompressed: int, archive_size: int, limits: IngestLimits
) -> None:
    if total_uncompressed > limits.max_total_uncompressed_bytes:
        raise IngestError(
            IngestRejection.UNCOMPRESSED_TOO_LARGE,
            f"This zip expands past {limits.max_total_uncompressed_bytes // MB} MB. "
            "Remove build folders or dependencies and try again.",
        )
    # Tiny archives cannot do real damage, and highly repetitive source files
    # legitimately compress well, so the ratio only applies above one file's size limit.
    ratio = total_uncompressed / max(archive_size, 1)
    if total_uncompressed > limits.max_file_bytes and ratio > limits.max_compression_ratio:
        raise IngestError(
            IngestRejection.COMPRESSION_RATIO,
            f"The archive expands to more than {limits.max_compression_ratio:g} times its size, "
            "which is typical of a zip bomb.",
        )


def _extract_members(
    zip_file: zipfile.ZipFile, members: list[_Member], destination: Path, limits: IngestLimits
) -> IngestResult:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    files: list[str] = []
    skipped: list[SkippedFile] = []

    for member in members:
        relative = member.path.as_posix()
        reason = skip_reason_for_path(member.path)
        if reason is not None:
            skipped.append(SkippedFile(path=relative, reason=reason))
            continue
        with zip_file.open(member.info) as source:
            head = _read_member(source, BINARY_SNIFF_BYTES)
            reason = skip_reason_for_content(member.info.file_size, head, limits.max_file_bytes)
            if reason is not None:
                skipped.append(SkippedFile(path=relative, reason=reason))
                continue
            target = _target_path(root, member.path)
            write_limited(chain((head,), _chunks(source)), target, member.info.file_size)
        files.append(relative)

    return IngestResult(
        root=root, files=sorted(files), skipped=sorted(skipped, key=lambda item: item.path)
    )


def write_limited(chunks: Iterable[bytes], target: Path, max_bytes: int) -> int:
    """Write ``chunks`` to a new file, refusing to write more than ``max_bytes``.

    Args:
        chunks: The file content, in pieces.
        target: File to create; parent directories are created. Must not exist.
        max_bytes: The size the archive declared for this file.

    Returns:
        The number of bytes written.

    Raises:
        IngestError: If the content is longer than declared.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("xb") as sink:
        for chunk in chunks:
            written += len(chunk)
            if written > max_bytes:
                raise IngestError(
                    IngestRejection.SIZE_MISMATCH,
                    "An archive entry is larger than its header declares. "
                    "The archive may be corrupt or deliberately malformed.",
                )
            sink.write(chunk)
    return written


def _chunks(source: IO[bytes]) -> Iterator[bytes]:
    while chunk := _read_member(source, _COPY_CHUNK_BYTES):
        yield chunk


def _read_member(source: IO[bytes], size: int) -> bytes:
    try:
        return source.read(size)
    except OSError as error:
        # bz2 reports corrupt compressed data as a bare OSError("Invalid data stream").
        # Only reads are converted, so disk errors while writing are not mislabeled.
        raise _corrupt_archive_error() from error


def _target_path(root: Path, relative: PurePosixPath) -> Path:
    target = root.joinpath(*relative.parts)
    # Names were already validated; this guards against anything that slipped through.
    if not target.resolve().is_relative_to(root):
        raise IngestError(
            IngestRejection.PATH_TRAVERSAL,
            f"The upload contains a path that points outside the project "
            f"({quote_name(relative.as_posix())}).",
        )
    return target


def _clear_directory(directory: Path) -> None:
    if not directory.is_dir():
        return
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
