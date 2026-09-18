"""Export order rows to CSV for the finance team."""

import csv
from pathlib import Path

FIELDS = ["id", "customer", "total"]


def export_orders(rows: list[dict[str, str]], path: Path) -> int:
    """Write ``rows`` to ``path`` and return how many were written."""
    handle = open(path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return len(rows)


def read_totals(path: Path) -> list[float]:
    """The ``total`` column of an exported file."""
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return [float(row["total"]) for row in csv.DictReader(handle)]
    finally:
        return []
