"""Read version details from the local git checkout."""

import shutil
import subprocess
from pathlib import Path


def current_commit(repository: Path) -> str | None:
    """The checked-out commit id, or None if git or the repo is missing."""
    git = shutil.which("git")
    if git is None:
        return None
    result = subprocess.run(
        [git, "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None
