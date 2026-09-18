import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import Settings
from evaluation.dataset import load_dataset
from evaluation.runner import FileRecord, RunKind, RunSpec, load_records, run, run_settings

SOURCE = "import os\n\n\ndef run(command):\n    os.system(command)\n"


def tiny_dataset(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "tool.py").write_text(SOURCE, encoding="utf-8")
    spec = {"dataset": "tiny", "version": 1, "description": "test", "labels": []}
    (root / "labels.json").write_text(json.dumps(spec), encoding="utf-8")
    return root


def record(name: str, *, complete: bool, run_name: str = "static") -> FileRecord:
    return FileRecord(
        run=run_name,
        file=name,
        started_at=datetime(2026, 9, 18, tzinfo=UTC),
        complete=complete,
        variants={},
        calls=[],
        stats={},
        durations_ms={},
        models={},
        prompt_versions={},
    )


@pytest.mark.parametrize(
    ("spec", "name", "variants"),
    [
        (RunSpec(RunKind.STATIC), "static", ("A",)),
        (RunSpec(RunKind.LLM_ONLY), "llm-only", ("B",)),
        (RunSpec(RunKind.HYBRID), "hybrid", ("D", "E")),
        (RunSpec(RunKind.MODEL, "nvidia"), "model-nvidia", ("F-nvidia",)),
    ],
)
def test_each_run_names_the_configurations_it_records(
    spec: RunSpec, name: str, variants: tuple[str, ...]
) -> None:
    assert (spec.name, spec.variants) == (name, variants)


@pytest.mark.parametrize(
    "spec_args",
    [(RunKind.MODEL, None), (RunKind.HYBRID, "nvidia"), (RunKind.MODEL, "openai")],
)
def test_a_provider_goes_with_model_runs_only(spec_args: tuple[RunKind, str | None]) -> None:
    with pytest.raises(ValueError, match="provider"):
        RunSpec(*spec_args)


def test_model_runs_disable_every_other_provider() -> None:
    base = Settings(
        _env_file=None,
        gemini_model="g",
        nvidia_model="n",
        hf_model_large="hl",
        hf_model_small="hs",
        local_model="l",
    )

    only = run_settings(RunSpec(RunKind.MODEL, "nvidia"), base)

    assert only.nvidia_model == "n"
    assert (only.gemini_model, only.hf_model_large, only.hf_model_small, only.local_model) == (
        None,
        None,
        None,
        None,
    )
    assert run_settings(RunSpec(RunKind.HYBRID), base) is base


def test_the_newest_record_for_a_file_wins(tmp_path: Path) -> None:
    path = tmp_path / "static.jsonl"
    lines = [
        record("a.py", complete=False),
        record("a.py", complete=True),
        record("b.py", complete=False),
    ]
    path.write_text("".join(r.model_dump_json() + "\n" for r in lines), encoding="utf-8")

    records = load_records(path)

    assert {name: r.complete for name, r in records.items()} == {"a.py": True, "b.py": False}


async def test_a_static_run_records_every_file_and_resumes(tmp_path: Path) -> None:
    dataset = load_dataset(tiny_dataset(tmp_path / "data"))
    runs = tmp_path / "runs"

    first = await run(RunSpec(RunKind.STATIC), dataset, runs_dir=runs)
    again = await run(RunSpec(RunKind.STATIC), dataset, runs_dir=runs)

    [result] = first.values()
    assert result.complete
    assert any(f.rule_id == "B605" for f in result.variants["A"])
    assert again == first, "complete files are not scanned twice"
    assert len((runs / "static.jsonl").read_text(encoding="utf-8").splitlines()) == 1
