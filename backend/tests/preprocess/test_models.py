import pytest
from pydantic import ValidationError

from app.preprocess.models import ChunkingConfig, LineRange, merge_ranges


def lr(start: int, end: int) -> LineRange:
    return LineRange(start=start, end=end)


def test_line_range_rejects_end_before_start_and_non_positive_lines() -> None:
    with pytest.raises(ValidationError):
        lr(5, 4)
    with pytest.raises(ValidationError):
        lr(0, 3)


def test_line_range_length_is_inclusive() -> None:
    assert lr(10, 10).length == 1
    assert lr(10, 19).length == 10


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (lr(1, 5), lr(5, 9), lr(5, 5)),
        (lr(1, 10), lr(3, 4), lr(3, 4)),
        (lr(1, 4), lr(5, 9), None),
    ],
)
def test_intersection(first: LineRange, second: LineRange, expected: LineRange | None) -> None:
    assert first.intersection(second) == expected
    assert second.intersection(first) == expected


@pytest.mark.parametrize(
    ("source", "removed", "expected"),
    [
        (lr(1, 10), lr(4, 6), [lr(1, 3), lr(7, 10)]),
        (lr(1, 10), lr(1, 6), [lr(7, 10)]),
        (lr(1, 10), lr(8, 20), [lr(1, 7)]),
        (lr(3, 5), lr(1, 10), []),
        (lr(1, 3), lr(7, 9), [lr(1, 3)]),
    ],
)
def test_without_removes_overlap(
    source: LineRange, removed: LineRange, expected: list[LineRange]
) -> None:
    assert source.without(removed) == expected


def test_merge_ranges_sorts_and_merges_overlapping_or_adjacent_ranges() -> None:
    merged = merge_ranges([lr(20, 25), lr(1, 3), lr(4, 6), lr(10, 12), lr(11, 15)])

    assert merged == [lr(1, 6), lr(10, 15), lr(20, 25)]


def test_chunking_config_rejects_target_above_max() -> None:
    with pytest.raises(ValidationError, match="target_lines"):
        ChunkingConfig(target_lines=600, max_lines=500)
