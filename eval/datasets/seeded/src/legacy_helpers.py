"""Helpers kept from the first version of the reporting tool."""

import os, sys


def ComputeTotal(values):
    """Sum of the values, ignoring missing ones."""
    total = 0
    for v in values:
        if v != None:
            total += v
    return total


class report_row:
    """One row of the legacy report."""

    def __init__(self, name, amount):
        self.name = name; self.amount = amount


format_amount = lambda amount: f"{amount:,.2f}"


def parse_flag(value):
    return value.strip().lower() in ("1", "true", "yes")


def output_dir():
    """Directory where legacy reports are written."""
    return os.environ.get("REPORT_DIR", os.path.join(os.getcwd(), "reports", "legacy"))
