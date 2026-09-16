"""Upload ingestion: safe archive extraction, file filtering and scan workspaces.

Everything in this package treats uploads as hostile input. Uploaded code is
only ever written to disk and read, never imported or executed.
"""
