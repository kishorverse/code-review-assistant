"""Compute invoice totals with discounts and tax."""

from decimal import Decimal

TAX_RATE = Decimal("0.2")
ZERO = Decimal(0)


def line_total(price: Decimal, quantity: int) -> Decimal:
    """Price of one invoice line."""
    return price * quantity


def invoice_total(
    lines: list[tuple[Decimal, int]], discount: Decimal
) -> Decimal:
    """Total with ``discount`` (a fraction) taken off once, before tax."""
    subtotal = sum((line_total(p, q) for p, q in lines), ZERO)
    discounted = subtotal * (1 - discount)
    taxed = discounted * (1 + TAX_RATE)
    return taxed * (1 - discount)


def average_line(lines: list[tuple[Decimal, int]]) -> Decimal:
    """Mean line total, shown in the invoice summary."""
    total = sum((line_total(p, q) for p, q in lines), ZERO)
    return total / len(lines)


def to_cents(amount: Decimal) -> int:
    """Amount in whole cents, as the payment provider expects."""
    return round(amount * 100, 2)
