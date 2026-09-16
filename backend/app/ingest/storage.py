"""Per-scan working directories under one storage root.

Each scan owns ``<root>/<scan_id>/upload`` for the raw upload,
``<root>/<scan_id>/source`` for the extracted files and ``scratch`` as the
analyzers' working directory. Scan ids must match the
format :func:`new_scan_id` produces, so a crafted id can never address a path
outside the storage root. Workspaces are deleted after a retention period to
honor the privacy promise that uploaded code is not kept.
"""

import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.errors import InvalidScanIdError

_SCAN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def new_scan_id() -> str:
    """Return a fresh, unguessable scan id."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class ScanWorkspace:
    """The directories that belong to one scan."""

    scan_id: str
    root: Path

    @property
    def upload_dir(self) -> Path:
        """Where the raw uploaded file is saved."""
        return self.root / "upload"

    @property
    def source_dir(self) -> Path:
        """Where the reviewable files are extracted."""
        return self.root / "source"

    @property
    def scratch_dir(self) -> Path:
        """Empty working directory for analyzer processes; never holds uploaded files."""
        return self.root / "scratch"


class ScanStorage:
    """Creates, finds and removes scan workspaces under ``root``.

    Methods perform blocking filesystem I/O; call them with ``asyncio.to_thread``
    from async code when the directories may be large.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def workspace(self, scan_id: str) -> ScanWorkspace:
        """Return the workspace for ``scan_id`` without touching the filesystem.

        Raises:
            InvalidScanIdError: If ``scan_id`` is not a Margin scan id.
        """
        if not _SCAN_ID_PATTERN.fullmatch(scan_id):
            raise InvalidScanIdError(f"Invalid scan id: {scan_id[:40]!r}")
        return ScanWorkspace(scan_id=scan_id, root=self._root / scan_id)

    def create(self, scan_id: str) -> ScanWorkspace:
        """Create an empty workspace.

        Raises:
            InvalidScanIdError: If ``scan_id`` is not a Margin scan id.
            FileExistsError: If the workspace already exists; ids are never reused.
        """
        workspace = self.workspace(scan_id)
        self._root.mkdir(parents=True, exist_ok=True)
        workspace.root.mkdir()
        workspace.upload_dir.mkdir()
        workspace.source_dir.mkdir()
        workspace.scratch_dir.mkdir()
        return workspace

    def delete(self, scan_id: str) -> None:
        """Remove a workspace and everything in it. Missing workspaces are ignored."""
        shutil.rmtree(self.workspace(scan_id).root, ignore_errors=True)

    def purge_expired(self, max_age: timedelta, now: datetime) -> list[str]:
        """Delete workspaces older than ``max_age``.

        Age is measured from the workspace directory's modification time, which
        is set when the workspace is created. Entries that are not scan
        workspace directories (including symlinks) are left alone, and a
        workspace deleted concurrently is simply skipped.

        Args:
            max_age: How long uploaded code may be kept.
            now: The current time, passed in so callers and tests control the clock.

        Returns:
            The ids of the deleted workspaces, sorted.
        """
        if not self._root.is_dir():
            return []
        cutoff = (now - max_age).timestamp()
        removed: list[str] = []
        for entry in sorted(self._root.iterdir()):
            if not _SCAN_ID_PATTERN.fullmatch(entry.name):
                continue
            try:
                status = entry.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(status.st_mode) and status.st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed.append(entry.name)
        return removed
