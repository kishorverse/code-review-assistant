"""Create and verify session tokens."""

import hashlib
import hmac
import secrets


def new_session_token() -> str:
    """A random, URL-safe session token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """The SHA-256 digest stored in place of the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()


def matches(token: str, stored_fingerprint: str) -> bool:
    """Whether ``token`` produces the stored fingerprint."""
    return hmac.compare_digest(token_fingerprint(token), stored_fingerprint)
