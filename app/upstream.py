import asyncio
import json
import time
from collections import OrderedDict
from itertools import cycle

import httpx

from .config import cache_max_entries, cache_ttl_s, upstream_urls


class ResponseCache:
    """Bounded LRU of upstream responses with a per-entry TTL."""

    def __init__(self, ttl_s: float, max_entries: int):
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, tuple[int, dict]]] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self._ttl_s > 0 and self._max_entries > 0

    def get(self, key: str) -> tuple[int, dict] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def put(self, key: str, value: tuple[int, dict]) -> None:
        self._entries[key] = (time.monotonic() + self._ttl_s, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)


def cache_key(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 ttl_s: float | None = None,
                 max_entries: int | None = None):
        self._urls = cycle(urls or upstream_urls())
        self._client = httpx.AsyncClient(timeout=None, transport=transport)
        self._cache = ResponseCache(
            cache_ttl_s() if ttl_s is None else ttl_s,
            cache_max_entries() if max_entries is None else max_entries,
        )
        self._inflight: dict[str, asyncio.Task] = {}

    async def forward(self, payload: dict) -> tuple[int, dict]:
        if not self._cache.enabled:
            return await self._fetch(payload)

        key = cache_key(payload)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch_and_store(key, payload))
            self._inflight[key] = task
        # shield so a cancelled waiter doesn't cancel the shared upstream call
        return await asyncio.shield(task)

    async def _fetch_and_store(self, key: str, payload: dict) -> tuple[int, dict]:
        try:
            result = await self._fetch(payload)
            if 200 <= result[0] < 300:
                self._cache.put(key, result)
            return result
        finally:
            self._inflight.pop(key, None)

    async def _fetch(self, payload: dict) -> tuple[int, dict]:
        url = next(self._urls)
        resp = await self._client.post(f"{url}/v1/completions", json=payload)
        return resp.status_code, resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()
