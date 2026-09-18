"""Pair incoming payments with the orders they settle."""


def pair_payments(
    orders: list[dict[str, str]], payments: list[dict[str, str]]
) -> list[tuple[str, str]]:
    """(order id, payment id) for each payment that names a known order."""
    return [
        (order["id"], payment["id"])
        for payment in payments
        for order in orders
        if order["id"] == payment["order_id"]
    ]


def repeated_payment_ids(payments: list[dict[str, str]]) -> set[str]:
    """Payment ids that appear more than once."""
    ids = [payment["id"] for payment in payments]
    return {pid for pid in ids if ids.count(pid) > 1}
