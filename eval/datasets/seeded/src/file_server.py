"""Serve files from the public downloads folder."""

from collections.abc import Iterator
from pathlib import Path

DOWNLOADS = Path("/srv/app/downloads")
CHUNK_SIZE = 64 * 1024


def resolve_download(name: str) -> Path:
    """Map a file name requested in a URL to its place in the folder."""
    return DOWNLOADS / name


def read_download(name: str) -> bytes:
    """Return the contents of a downloadable file."""
    path = resolve_download(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    return path.read_bytes()


def stream_download(name: str) -> Iterator[bytes]:
    """Yield a file in chunks, so large downloads use little memory."""
    with resolve_download(name).open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            yield chunk
