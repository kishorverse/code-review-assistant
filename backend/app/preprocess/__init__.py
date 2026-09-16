"""Preprocessing: detect each file's language, parse it, and split it into review chunks.

Chunks follow code structure, stay within the size limit an LLM call can
handle, carry real file line numbers, and record regions that failed to parse
so incomplete code is handled gracefully instead of reported as broken.
"""
