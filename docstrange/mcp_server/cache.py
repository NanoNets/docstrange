"""LRU extraction result cache keyed on file identity (path + mtime + size).

Using filesystem stat rather than MD5 means zero hashing overhead on every
call. A file that is modified in-place will have a changed mtime/size and
automatically get a fresh extraction.
"""

import os
from collections import OrderedDict
from typing import Any, List, Optional, Tuple


class ExtractionCache:
    """Thread-unsafe LRU cache for EngineeringDrawingResult objects.

    The MCP server runs in a single asyncio event loop so no locking is needed.
    """

    def __init__(self, maxsize: int = 20) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = max(1, maxsize)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, path: str, extractors: Optional[List[str]]) -> Tuple:
        stat = os.stat(path)
        return (path, stat.st_mtime, stat.st_size, tuple(sorted(extractors or [])))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, path: str, extractors: Optional[List[str]]) -> Optional[Any]:
        """Return cached result or ``None`` on a miss."""
        try:
            key = self._key(path, extractors)
        except OSError:
            return None
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, path: str, extractors: Optional[List[str]], value: Any) -> None:
        """Store *value* in the cache, evicting the LRU entry if full."""
        try:
            key = self._key(path, extractors)
        except OSError:
            return
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)
