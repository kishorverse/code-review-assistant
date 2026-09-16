"""Error hierarchy for Margin.

Every error raised deliberately by the application derives from
:class:`MarginError`, so API handlers and pipeline stages can tell expected
failures apart from programming errors.
"""


class MarginError(Exception):
    """Base class for all errors raised by Margin."""
