"""Create and restore tar backups of a project directory."""

import subprocess
import tarfile
from pathlib import Path


def create_backup(project: Path, label: str) -> Path:
    """Archive ``project`` into ``backups/<label>.tar.gz``."""
    target = Path("backups") / f"{label}.tar.gz"
    target.parent.mkdir(exist_ok=True)
    subprocess.run(
        f"tar czf {target} -C {project} .", shell=True, check=True
    )
    return target


def restore_backup(archive: Path, destination: Path) -> None:
    """Unpack a backup archive uploaded by a user into ``destination``."""
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination)


def backup_size(archive: Path) -> int:
    """Total size in bytes of the files inside ``archive``."""
    with tarfile.open(archive) as bundle:
        return sum(member.size for member in bundle.getmembers())
