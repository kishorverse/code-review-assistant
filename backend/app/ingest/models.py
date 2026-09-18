"""Limits and result types shared by the ingest modules."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, PositiveFloat, PositiveInt

MB = 1024 * 1024


class IngestLimits(BaseModel):
    """Upper bounds that keep a single upload from exhausting disk, memory or time."""

    model_config = ConfigDict(frozen=True)

    max_archive_bytes: PositiveInt = 20 * MB
    max_total_uncompressed_bytes: PositiveInt = 80 * MB
    max_files: PositiveInt = 2_000
    max_compression_ratio: PositiveFloat = 100.0
    max_file_bytes: PositiveInt = 1 * MB
    max_path_length: PositiveInt = 400


class SkipReason(StrEnum):
    """Why a file was left out of the review. Skipping is not an error."""

    EXCLUDED_DIRECTORY = "excluded_directory"
    LOCKFILE = "lockfile"
    MINIFIED = "minified"
    TOO_LARGE = "too_large"
    BINARY = "binary"
    SYMLINK = "symlink"
    INVALID_NAME = "invalid_name"
    SPECIAL_FILE = "special_file"
    UNREADABLE = "unreadable"


class SkippedFile(BaseModel):
    """A file that was present in the upload but not extracted."""

    model_config = ConfigDict(frozen=True, json_schema_serialization_defaults_required=True)

    path: str
    reason: SkipReason


class IngestResult(BaseModel):
    """What was extracted into a scan's source directory.

    Attributes:
        root: Directory containing the extracted files.
        files: Extracted file paths, POSIX-style and relative to ``root``, sorted.
        skipped: Files left out, with the reason for each.
    """

    model_config = ConfigDict(frozen=True)

    root: Path
    files: list[str]
    skipped: list[SkippedFile]
