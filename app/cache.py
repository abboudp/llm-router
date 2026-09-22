"""Small in-process LRU + TTL cache for upstream completions.

Upstream completions are deterministic per (prompt, max_tokens) — the same
prompt always yields the same completion and signature — so serving a repeat
from memory is indistinguishable from asking a replica again, only ~100x faster.
"""
import json
import time
from collections import OrderedDict


class ResponseCache:
    def __init__(self, max_entries: int = 1024, ttl_s: float = 300.0):
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self._items: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self.max_entries > 0

    @staticmethod
    def key(payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        entry = self._items.get(key)
        if entry is None or entry[0] < time.monotonic():
            if entry is not None:
                del self._items[key]
            self.misses += 1
            return None
        self._items.move_to_end(key)
        self.hits += 1
        return entry[1]

    def put(self, key: str, body: dict) -> None:
        if not self.enabled:
            return
        self._items[key] = (time.monotonic() + self.ttl_s, body)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "max_entries": self.max_entries,
            "ttl_s": self.ttl_s,
            "entries": len(self._items),
            "hits": self.hits,
            "misses": self.misses,
        }
