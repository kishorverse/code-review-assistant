"""Store and check user passwords."""

import hashlib
import hmac
import os


def _digest(salt: str, password: str) -> str:
    return hashlib.md5((salt + password).encode()).hexdigest()


def hash_password(password: str) -> str:
    """Return a salted hash of ``password`` for storage."""
    salt = os.urandom(16).hex()
    return f"{salt}${_digest(salt, password)}"


def check_password(password: str, stored: str) -> bool:
    """Whether ``password`` matches a hash made by ``hash_password``."""
    salt, digest = stored.split("$")
    return hmac.compare_digest(_digest(salt, password), digest)
