"""Decide which uploaded files are worth reviewing.

Vendored dependencies, tool caches, build output, lockfiles, minified bundles
and binaries are left out before any analyzer or LLM sees them. That keeps
scans fast and focused on code the user actually wrote.
"""

from pathlib import PurePosixPath

from app.ingest.models import SkipReason

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "bower_components",
        "venv",
        ".venv",
        "site-packages",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".eggs",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        "htmlcov",
        ".idea",
        ".vscode",
    }
)

LOCKFILES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "poetry.lock",
        "pdm.lock",
        "pipfile.lock",
        "uv.lock",
        "cargo.lock",
        "composer.lock",
        "gemfile.lock",
        "go.sum",
    }
)

GENERATED_SUFFIXES = (".min.js", ".min.mjs", ".min.css", ".js.map", ".css.map")

# A NUL byte in the first block is a reliable, cheap signal for binary content.
# UTF-16 text also contains NUL bytes and is skipped too, which is acceptable for source review.
BINARY_SNIFF_BYTES = 8192


def skip_reason_for_path(path: PurePosixPath) -> SkipReason | None:
    """Return why a file should be skipped based on its location and name, if at all."""
    if any(directory.lower() in EXCLUDED_DIRECTORIES for directory in path.parts[:-1]):
        return SkipReason.EXCLUDED_DIRECTORY
    name = path.name.lower()
    if name in LOCKFILES:
        return SkipReason.LOCKFILE
    if name.endswith(GENERATED_SUFFIXES):
        return SkipReason.MINIFIED
    return None


def skip_reason_for_content(size: int, head: bytes, max_file_bytes: int) -> SkipReason | None:
    """Return why a file should be skipped based on its size and first bytes, if at all.

    Args:
        size: Uncompressed size of the file in bytes.
        head: The first bytes of the file; at least ``BINARY_SNIFF_BYTES`` when available.
        max_file_bytes: Largest file that is reviewed.
    """
    if size > max_file_bytes:
        return SkipReason.TOO_LARGE
    if b"\x00" in head[:BINARY_SNIFF_BYTES]:
        return SkipReason.BINARY
    return None
