"""Summary statistics for response-time samples."""


def mean(samples: list[float]) -> float:
    """Arithmetic mean of the samples."""
    if not samples:
        raise ValueError("no samples")
    return sum(samples) / len(samples)


def median(samples: list[float]) -> float:
    """Middle value of the samples."""
    middle = len(samples) // 2
    if len(samples) % 2:
        return samples[middle]
    return (samples[middle - 1] + samples[middle]) / 2


def percentile(samples: list[float], fraction: float) -> float:
    """Value below which ``fraction`` (0 to 1) of the samples fall."""
    ordered = sorted(samples)
    index = int(fraction * len(ordered))
    return ordered[index]
