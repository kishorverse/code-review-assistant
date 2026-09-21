import re
from pathlib import Path

import pytest

from evaluation import robustness
from evaluation.robustness import REPOSITORIES, CloneError, Repository, Scan, prepare, to_markdown

COMMIT = re.compile(r"^[0-9a-f]{40}$")

SCANNED = Scan(
    repository="psf/requests",
    language="Python",
    commit="dae7ef6",
    ingested=124,
    reviewed=37,
    skipped=7,
    languages={"python": 37},
    kloc=7.75,
    seconds=6.2,
    severities={"critical": 0, "high": 15, "medium": 111, "low": 625},
    categories={"style": 365},
    tools={"ruff": "ok", "bandit": "ok", "opengrep": "skipped"},
    rules={"E501": 289},
    score=0,
    grade="E",
)


def test_every_repository_is_pinned_to_a_full_commit_and_named_once() -> None:
    names = [repository.name for repository in REPOSITORIES]

    assert len(names) == len(set(names))
    assert all(COMMIT.match(repository.commit) for repository in REPOSITORIES)
    assert all(repository.license for repository in REPOSITORIES)
    # One repository per supported language keeps the table's coverage honest.
    assert {repository.language for repository in REPOSITORIES} == {
        "Python",
        "JavaScript",
        "TypeScript",
        "Go",
        "Java",
    }


def test_a_scan_counts_only_the_analyzers_that_ran() -> None:
    assert SCANNED.tools_ran == 2
    assert SCANNED.findings == 751


def test_the_tables_report_what_ran_and_what_it_found() -> None:
    table = to_markdown([SCANNED])

    assert (
        "| psf/requests | Python | `dae7ef6` | 124 | 37 | python 37 | 2 of 3 | 6.2 | 358 |" in table
    )
    assert "| psf/requests | 7.8 | 0 | 15 | 111 | 625 | 97 | 0/100 (E) | E501 (289) |" in table
    assert "Failures:" not in table


def test_a_repository_that_could_not_be_scanned_is_listed_rather_than_dropped() -> None:
    rejected = Scan(
        repository="big/repo",
        language="Go",
        commit="abc1234",
        error="IngestError: too many files",
    )

    table = to_markdown([SCANNED, rejected])

    assert "| big/repo |" not in table
    assert "- **big/repo**: IngestError: too many files" in table


def test_an_analyzer_that_failed_is_reported_but_a_skipped_one_is_not() -> None:
    failed = Scan(
        repository="psf/requests",
        language="Python",
        commit="dae7ef6",
        tools={"mypy": "failed", "ruff": "skipped", "bandit": "ok"},
    )

    table = to_markdown([failed])

    assert "- **psf/requests**: mypy failed" in table
    assert "ruff skipped" not in table


async def test_a_checkout_already_at_the_pinned_commit_is_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = REPOSITORIES[0]
    (tmp_path / repository.name.replace("/", "__") / ".git").mkdir(parents=True)
    calls: list[tuple[str, ...]] = []

    async def fake_git(*args: str, cwd: Path) -> str:
        calls.append(args)
        return repository.commit

    monkeypatch.setattr(robustness, "_git", fake_git)

    path = await prepare(repository, tmp_path)

    assert path == tmp_path / "psf__requests"
    assert calls == [("rev-parse", "HEAD")]


async def test_a_missing_checkout_is_fetched_at_its_pinned_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Repository("a/b", "https://example.test/b.git", "0" * 40, "Go", "MIT")
    calls: list[tuple[str, ...]] = []

    async def fake_git(*args: str, cwd: Path) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(robustness, "_git", fake_git)

    path = await prepare(repository, tmp_path)

    assert path.is_dir()
    assert [args[0] for args in calls] == ["init", "fetch", "checkout", "clean"]
    # Depth 1 on one commit: the code, not its history.
    assert calls[1] == ("fetch", "--depth", "1", "--quiet", repository.url, repository.commit)


async def test_an_interrupted_checkout_is_discarded_and_fetched_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = REPOSITORIES[0]
    checkout = tmp_path / repository.name.replace("/", "__")
    (checkout / ".git").mkdir(parents=True)
    (checkout / "stale.py").write_text("x = 1", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    async def fake_git(*args: str, cwd: Path) -> str:
        calls.append(args)
        if args[0] == "rev-parse":
            raise CloneError("not a git repository")
        return ""

    monkeypatch.setattr(robustness, "_git", fake_git)

    await prepare(repository, tmp_path)

    assert not (checkout / "stale.py").exists()
    assert [args[0] for args in calls] == ["rev-parse", "init", "fetch", "checkout", "clean"]
