import ast

import pytest

from evaluation.latency import Measurement, synthetic_source, to_markdown


@pytest.mark.parametrize("lines", [50, 200, 500])
def test_synthetic_sources_are_valid_python_of_about_the_requested_size(lines: int) -> None:
    source = synthetic_source(lines)

    ast.parse(source)
    assert lines <= source.count("\n") < lines + 15
    assert synthetic_source(lines) == source


def test_the_table_reports_medians_per_input_and_mode() -> None:
    stages = {"analyzing": 2.0, "reviewing": 0.0, "verifying": 0.0, "summarizing": 0.0}
    measurements = [
        Measurement("50 lines", "static", seconds, stages, calls=0, files=1)
        for seconds in (3.0, 4.0, 5.0)
    ]

    table = to_markdown(measurements)

    assert "| 50 lines | static | 3 | 4.0 | 4.9 | 2.0 | 0.0 | 0.0 | 0.0 | 0 | 15.0 |" in table
