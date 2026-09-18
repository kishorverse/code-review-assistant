"""Exact money arithmetic for invoices."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_money(value: str) -> Decimal:
    """Parse a decimal string such as ``"12.50"`` into an exact amount."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def split_evenly(total: Decimal, parts: int) -> list[Decimal]:
    """Split ``total`` into ``parts`` amounts that add up to it exactly.

    The first amounts absorb the leftover cents, so no cent is lost.
    """
    if parts < 1:
        raise ValueError("parts must be at least 1")
    if total != total.quantize(CENT):
        raise ValueError("total must be a whole number of cents")
    cents = int(total / CENT)
    share, leftover = divmod(cents, parts)
    return [
        (share + (1 if index < leftover else 0)) * CENT
        for index in range(parts)
    ]
