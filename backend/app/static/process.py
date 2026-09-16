"""Run analyzer processes safely.

Commands are argument lists, never shell strings. Each process gets a minimal
environment: none of the backend's variables (and so none of its API keys)
are passed on, and home and temp directories point at a scratch directory
so user-level tool configuration is not picked up either.
"""

import asyncio
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.errors import ToolUnavailableError

# Variables Windows needs for any process to start; they are not configuration.
_PLATFORM_VARIABLES = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")


@dataclass(frozen=True)
class ProcessResult:
    """Exit code, decoded output and wall-clock duration of a finished process."""

    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


def python_tool(module: str, *arguments: str) -> list[str]:
    """Command that runs a Python analyzer with the backend's own interpreter.

    Using ``sys.executable -m`` pins the tool to the locked version installed
    alongside the backend instead of whatever is on ``PATH``.

    ``-I`` (isolated mode) is essential: plain ``python -m`` puts the working
    directory first on ``sys.path``, so an uploaded file named like a module
    the tool imports (``json.py``, ``detect_secrets.py``) would be executed.
    Isolated mode also ignores ``PYTHON*`` variables, so ``-B`` and ``-X utf8``
    are passed as flags instead.
    """
    return [sys.executable, "-I", "-B", "-X", "utf8", "-m", module, *arguments]


def minimal_environment(scratch: Path, platform: Mapping[str, str] = os.environ) -> dict[str, str]:
    """Build the environment for an analyzer process.

    Args:
        scratch: Empty directory used as home and temp directory.
        platform: Source of the few platform variables processes need to start.
    """
    environment = {
        "PATH": os.pathsep.join([str(Path(sys.executable).parent), *_system_paths(platform)]),
        "HOME": str(scratch),
        "USERPROFILE": str(scratch),
        "TMPDIR": str(scratch),
        "TEMP": str(scratch),
        "TMP": str(scratch),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment.update({name: platform[name] for name in _PLATFORM_VARIABLES if name in platform})
    return environment


async def run_process(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> ProcessResult:
    """Run a command to completion and capture its output.

    There is no timeout here: callers wrap the call in ``asyncio.timeout``, and
    cancellation (including a timeout) kills the process before re-raising.

    Raises:
        ToolUnavailableError: If the executable does not exist.
    """
    started = time.perf_counter()
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=dict(env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise ToolUnavailableError(f"{Path(argv[0]).name} is not installed") from error

    try:
        stdout, stderr = await process.communicate()
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise

    return ProcessResult(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        duration_ms=round((time.perf_counter() - started) * 1000),
    )


def _system_paths(platform: Mapping[str, str]) -> list[str]:
    if sys.platform == "win32":
        root = platform.get("SYSTEMROOT", r"C:\Windows")
        return [str(Path(root) / "System32"), root]
    return ["/usr/local/bin", "/usr/bin", "/bin"]
