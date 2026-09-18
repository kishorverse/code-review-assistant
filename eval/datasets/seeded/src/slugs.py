"""Turn article titles into URL slugs."""

import re
import unicodedata

_NOT_ALLOWED = re.compile(r"[^a-z0-9]+")
MAX_LENGTH = 60


def slugify(title: str) -> str:
    """A lowercase ASCII slug such as ``"cafe-menu"`` for ``"Café Menu"``.

    Accents are removed, runs of other characters become one hyphen, and
    the slug is cut at a hyphen so that no word is split.
    """
    ascii_title = (
        unicodedata.normalize("NFKD", title)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = _NOT_ALLOWED.sub("-", ascii_title.lower()).strip("-")
    if len(slug) <= MAX_LENGTH:
        return slug
    cut = slug.rfind("-", 0, MAX_LENGTH + 1)
    return slug[: cut if cut > 0 else MAX_LENGTH]
