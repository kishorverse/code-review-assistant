from pathlib import Path

from app.static.base import AnalysisTarget, absolute_paths, relative_to_root


def make_target(tmp_path: Path) -> AnalysisTarget:
    root = (tmp_path / "source").resolve()
    root.mkdir()
    return AnalysisTarget(
        root=root,
        files=("pkg/app.py", "pkg/UTIL.PY", "web/app.js", "README.md"),
        scratch=tmp_path / "scratch",
    )


def test_files_with_suffix_ignores_case(tmp_path: Path) -> None:
    target = make_target(tmp_path)

    assert target.files_with_suffix(".py") == ["pkg/app.py", "pkg/UTIL.PY"]
    assert target.files_with_suffix(".js", ".ts") == ["web/app.js"]


def test_relative_to_root_accepts_absolute_and_relative_reports(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    absolute = str(target.root / "pkg" / "app.py")

    assert relative_to_root(absolute, target.root) == "pkg/app.py"
    assert relative_to_root("pkg\\app.py" if "\\" in absolute else "pkg/app.py", target.root) == (
        "pkg/app.py"
    )


def test_relative_to_root_rejects_paths_outside_the_root(tmp_path: Path) -> None:
    target = make_target(tmp_path)

    assert relative_to_root(tmp_path / "elsewhere.py", target.root) is None
    assert relative_to_root("../escape.py", target.root) is None


def test_absolute_paths_join_posix_names_to_the_root(tmp_path: Path) -> None:
    target = make_target(tmp_path)

    assert absolute_paths(target, ["pkg/app.py"]) == [str(target.root / "pkg" / "app.py")]
