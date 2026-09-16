import asyncio
import sys
import time
from pathlib import Path

import pytest

from app.errors import ToolUnavailableError
from app.static.process import minimal_environment, python_tool, run_process

SENTINEL = "value-that-must-not-reach-analyzers"
PRINT_ENV = "import json, os; print(json.dumps(dict(os.environ)))"


async def test_runs_command_and_captures_output(tmp_path: Path) -> None:
    code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"

    result = await run_process(
        [sys.executable, "-c", code], cwd=tmp_path, env=minimal_environment(tmp_path)
    )

    assert result.returncode == 3
    assert result.stdout.strip() == "out"
    assert result.stderr.strip() == "err"
    assert result.duration_ms >= 0


async def test_environment_does_not_leak_backend_secrets(tmp_path: Path) -> None:
    platform = {"SYSTEMROOT": r"C:\Windows", "NVIDIA_API_KEY": SENTINEL}

    env = minimal_environment(tmp_path, platform)
    result = await run_process([sys.executable, "-c", PRINT_ENV], cwd=tmp_path, env=env)

    assert "NVIDIA_API_KEY" not in env
    assert SENTINEL not in result.stdout
    assert env["HOME"] == str(tmp_path)
    assert env["SYSTEMROOT"] == r"C:\Windows"


async def test_runs_in_the_given_working_directory(tmp_path: Path) -> None:
    result = await run_process(
        [sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd=tmp_path,
        env=minimal_environment(tmp_path),
    )

    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


async def test_cancellation_kills_the_process(tmp_path: Path) -> None:
    marker = tmp_path / "finished"
    code = f"import time, pathlib; time.sleep(5); pathlib.Path({str(marker)!r}).touch()"
    started = time.perf_counter()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.5):
            await run_process(
                [sys.executable, "-c", code], cwd=tmp_path, env=minimal_environment(tmp_path)
            )

    assert time.perf_counter() - started < 4
    await asyncio.sleep(0.2)
    assert not marker.exists()


async def test_missing_executable_is_reported_as_unavailable(tmp_path: Path) -> None:
    with pytest.raises(ToolUnavailableError, match="definitely-not-installed"):
        await run_process(
            [str(tmp_path / "definitely-not-installed")],
            cwd=tmp_path,
            env=minimal_environment(tmp_path),
        )


def test_python_tool_uses_the_backend_interpreter() -> None:
    assert python_tool("ruff", "check") == [sys.executable, "-m", "ruff", "check"]
