"""Preprocess one extracted file: detect its language, parse it and chunk it."""

from pathlib import Path, PurePosixPath

from app.languages.base import LanguageAdapter
from app.languages.registry import LanguageRegistry
from app.preprocess.chunker import build_chunks, split_lines
from app.preprocess.detect import detect_language
from app.preprocess.models import ChunkingConfig, LineRange, PreprocessedFile, merge_ranges
from app.preprocess.parse import parse_source
from app.preprocess.structure import header_ranges, segment_file

_SHEBANG_SNIFF_BYTES = 256


def preprocess_file(
    root: Path, file_path: str, registry: LanguageRegistry, config: ChunkingConfig
) -> PreprocessedFile | None:
    """Detect, parse and chunk one file from a scan's source directory.

    This is blocking I/O and CPU work; call it with ``asyncio.to_thread`` from
    async code.

    Args:
        root: The scan's source directory.
        file_path: POSIX path relative to ``root``, as produced by ingestion.
        registry: The available language adapters.
        config: Chunk size limits.

    Returns:
        The preprocessed file, or ``None`` if Margin does not review its language.
    """
    source = root.joinpath(*PurePosixPath(file_path).parts).read_bytes()
    adapter = detect_language(PurePosixPath(file_path), source[:_SHEBANG_SNIFF_BYTES], registry)
    if adapter is None:
        return None
    return preprocess_source(file_path, source, adapter, config)


def preprocess_source(
    file_path: str, source: bytes, adapter: LanguageAdapter, config: ChunkingConfig
) -> PreprocessedFile:
    """Parse and chunk source whose language is already known.

    Bytes that are not valid UTF-8 are replaced for display only; parsing
    uses the original bytes, and line numbers stay aligned because newline
    bytes are never altered by decoding.
    """
    lines = split_lines(source.decode("utf-8-sig", errors="replace"))
    parsed = parse_source(source, adapter)
    root = parsed.tree.root_node
    partial_regions = _within_file(parsed.partial_regions, len(lines))
    segments = segment_file(root, len(lines), adapter, config.max_lines)
    chunks = build_chunks(
        file_path=file_path,
        language=adapter.name,
        lines=lines,
        segments=segments,
        header=header_ranges(root, adapter),
        partial_regions=partial_regions,
        config=config,
    )
    return PreprocessedFile(
        path=file_path,
        language=adapter.name,
        support=adapter.support,
        line_count=len(lines),
        partial_regions=partial_regions,
        chunks=chunks,
    )


def _within_file(regions: list[LineRange], line_count: int) -> list[LineRange]:
    """Clamp regions to the file's last line.

    A token missing at the very end of a truncated file sits one row past the
    last line; clamping keeps the signal that the file ends incomplete.
    """
    if line_count == 0:
        return []
    return merge_ranges(
        LineRange(start=min(region.start, line_count), end=min(region.end, line_count))
        for region in regions
    )
