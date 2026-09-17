from app.static.analyzers.lizard import LizardAnalyzer, parse_output
from tests.static.conftest import TargetFactory, by_rule


def js_branchy(name: str, branches: int) -> str:
    body = "".join(f"  if (v === {n}) {{ return {n}; }}\n" for n in range(branches))
    return f"function {name}(v) {{\n{body}  return -1;\n}}\n"


PYTHON_WIDE = """
    def configure(host, port, user, timeout, retries, verbose, cache, region):
        return host
"""


async def test_measures_functions_and_flags_complexity_and_parameters(
    make_target: TargetFactory,
) -> None:
    target = make_target({"web/route.js": js_branchy("route", 20), "cfg/setup.py": PYTHON_WIDE})

    result = await LizardAnalyzer().analyze(target)

    findings = by_rule(result.findings)
    assert findings["function-complexity"].file_path == "web/route.js"
    assert findings["too-many-parameters"].file_path == "cfg/setup.py"
    metrics = {m.path: m for m in result.metrics}
    [route] = metrics["web/route.js"].functions
    assert (route.name, route.start_line, route.cyclomatic_complexity) == ("route", 1, 21)
    assert metrics["cfg/setup.py"].functions[0].parameters == 8


async def test_gitignore_inside_the_upload_cannot_hide_code(make_target: TargetFactory) -> None:
    target = make_target({"web/route.js": js_branchy("route", 20), ".gitignore": "*\n"})

    result = await LizardAnalyzer().analyze(target)

    assert "function-complexity" in by_rule(result.findings)
    assert [metric.path for metric in result.metrics] == ["web/route.js"]


async def test_python_complexity_is_left_to_radon(make_target: TargetFactory) -> None:
    branches = "".join(f"    if v == {n}:\n        return {n}\n" for n in range(20))
    target = make_target({"app/route.py": f"def route(v):\n{branches}    return -1\n"})

    result = await LizardAnalyzer().analyze(target)

    assert "function-complexity" not in by_rule(result.findings)
    assert result.metrics[0].functions[0].cyclomatic_complexity == 21


def test_parse_ignores_rows_for_files_outside_the_review_and_malformed_rows(
    make_target: TargetFactory,
) -> None:
    target = make_target({"a.py": "x = 1\n"})
    rows = [
        f'5,1,20,1,90,"f@1-90@x",{target.root / "a.py"},f,f( ),1,90',
        f'5,1,20,1,5,"g@1-5@x",{target.root / "notes.c"},g,g( ),1,5',
        "not,a,valid,row",
    ]

    findings, metrics = parse_output("\n".join(rows), target)

    assert [f.rule_id for f in findings] == ["long-function"]
    assert [m.path for m in metrics] == ["a.py"]
