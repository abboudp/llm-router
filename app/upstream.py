import asyncio
import copy
from collections import OrderedDict
from collections.abc import Hashable
from itertools import cycle

import httpx

from .config import cache_enabled, cache_max_entries, upstream_urls


class ResponseCache:
    """LRU cache of successful upstream responses with single-flight misses.

    All mutations happen synchronously between awaits, so the structure is
    safe under a single asyncio event loop without an explicit lock.
    """

    def __init__(self, max_entries: int):
        self.max_entries = max_entries
        self._entries: OrderedDict[Hashable, dict] = OrderedDict()
        self.inflight: dict[Hashable, asyncio.Future] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: Hashable) -> dict | None:
        body = self._entries.get(key)
        if body is None:
            return None
        self._entries.move_to_end(key)
        return copy.deepcopy(body)

    def put(self, key: Hashable, body: dict) -> None:
        self._entries[key] = copy.deepcopy(body)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


def _cache_key(payload: dict) -> Hashable | None:
    key = (payload.get("prompt"), payload.get("max_tokens"))
    try:
        hash(key)
    except TypeError:
        return None
    return key


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 cache: bool | None = None,
                 cache_size: int | None = None):
        self._urls = cycle(urls or upstream_urls())
        self._client = httpx.AsyncClient(timeout=None, transport=transport)
        enabled = cache_enabled() if cache is None else cache
        size = cache_max_entries() if cache_size is None else cache_size
        self._cache = ResponseCache(size) if enabled and size > 0 else None

    async def forward(self, payload: dict) -> tuple[int, dict]:
        key = _cache_key(payload) if self._cache is not None else None
        if key is None:
            return await self._post(payload)
        return await self._forward_cached(key, payload)

    async def _post(self, payload: dict) -> tuple[int, dict]:
        url = next(self._urls)
        resp = await self._client.post(f"{url}/v1/completions", json=payload)
        return resp.status_code, resp.json()

    async def _forward_cached(self, key: Hashable, payload: dict) -> tuple[int, dict]:
        cache = self._cache
        assert cache is not None
        hit = cache.get(key)
        if hit is not None:
            return 200, hit

        leader = cache.inflight.get(key)
        if leader is not None:
            shared = await asyncio.shield(leader)
            if shared is not None:
                return 200, copy.deepcopy(shared)
            # leader failed or returned an error: make an independent attempt
            status, body = await self._post(payload)
            if status == 200:
                cache.put(key, body)
            return status, body

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        cache.inflight[key] = fut
        result: dict | None = None
        try:
            status, body = await self._post(payload)
            if status == 200:
                cache.put(key, body)
                result = body
            return status, body
        finally:
            cache.inflight.pop(key, None)
            if not fut.done():
                fut.set_result(copy.deepcopy(result) if result is not None else None)

    async def aclose(self) -> None:
        await self._client.aclose()
