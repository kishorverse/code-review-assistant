"""Static analysis engine: run open-source analyzers and normalize their output.

Analyzers only read uploaded files. Each runs as a separate process from an
empty working directory with a minimal environment, and with the tool's
project-configuration discovery and plugin loading disabled, so an upload
can never make a tool execute code it contains.
"""
