"""Estimate shipping costs by destination."""

RATES = {"domestic": 4.5, "europe": 12.0, "world": 25.0}


def rate_for(region: str) -> float:
    """Flat rate for a region."""
    return RATES.get(region)


def estimate(region: str, weight_kg: float) -> float:
    """The flat rate, plus 1.5 for every kilogram over 2 kg."""
    extra = max(0, weight_kg - 2) * 1.5
    return rate_for(region) + extra


def region_label(region: str) -> str:
    """Human-readable region name printed on the invoice."""
    names = {"domestic": "Domestic", "europe": "Europe"}
    return names[region]
