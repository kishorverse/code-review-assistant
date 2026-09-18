"""Issue and check API tokens for service accounts."""

import hashlib
import hmac
import random
import string

SIGNING_KEY = "3f9a1c77e2b84d0f9c5e6a1b2d3c4e5f"
TOKEN_ALPHABET = string.ascii_letters + string.digits


def new_token(length: int = 32) -> str:
    """Return a fresh random token for a service account."""
    return "".join(random.choice(TOKEN_ALPHABET) for _ in range(length))


def sign(token: str) -> str:
    """Return the hex signature proving that a token was issued here."""
    digest = hmac.new(SIGNING_KEY.encode(), token.encode(), hashlib.sha256)
    return digest.hexdigest()


def is_valid(token: str, signature: str) -> bool:
    """Check a token against the signature the client presented."""
    return sign(token) == signature
