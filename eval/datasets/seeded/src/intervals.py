"""Merge overlapping booking intervals."""

Interval = tuple[int, int]


def merge(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping or touching ``(start, end)`` intervals.

    The input may be in any order; the result is sorted by start.
    """
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            last_start, last_end = merged[-1]
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def total_length(intervals: list[Interval]) -> int:
    """Length covered by the intervals, counting overlaps once."""
    return sum(end - start for start, end in merge(intervals))
