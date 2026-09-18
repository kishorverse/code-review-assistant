"""A small least-recently-used cache for rendered pages."""

from collections import OrderedDict


class PageCache:
    """Keeps the most recently used pages, up to ``capacity`` of them."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._pages: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        """The cached page, which now counts as recently used."""
        return self._pages.get(key)

    def put(self, key: str, page: str) -> None:
        """Store a page, evicting the least recently used one if full."""
        self._pages[key] = page
        self._pages.move_to_end(key)
        if len(self._pages) > self.capacity:
            self._pages.popitem(last=True)

    def drop_prefix(self, prefix: str) -> None:
        """Remove every cached page whose key starts with ``prefix``."""
        for key in self._pages:
            if key.startswith(prefix):
                del self._pages[key]
