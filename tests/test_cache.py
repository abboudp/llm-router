import asyncio
import json

import httpx

from app.config import cache_max_entries, cache_ttl_s
from app.upstream import ResponseCache, UpstreamPool, cache_key


def test_cache_config_defaults(monkeypatch):
    monkeypatch.delenv("RESPONSE_CACHE_TTL_S", raising=False)
    monkeypatch.delenv("RESPONSE_CACHE_MAX_ENTRIES", raising=False)
    assert cache_ttl_s() == 60
    assert cache_max_entries() == 1024


def test_cache_config_env(monkeypatch):
    monkeypatch.setenv("RESPONSE_CACHE_TTL_S", "2.5")
    monkeypatch.setenv("RESPONSE_CACHE_MAX_ENTRIES", "7")
    assert cache_ttl_s() == 2.5
    assert cache_max_entries() == 7


def test_cache_key_is_order_insensitive():
    assert cache_key({"prompt": "p", "max_tokens": 64}) == cache_key({"max_tokens": 64, "prompt": "p"})
    assert cache_key({"prompt": "p", "max_tokens": 64}) != cache_key({"prompt": "p", "max_tokens": 32})


def test_response_cache_lru_eviction_and_ttl(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("app.upstream.time.monotonic", lambda: now[0])
    cache = ResponseCache(ttl_s=10, max_entries=2)
    cache.put("a", (200, {"v": "a"}))
    cache.put("b", (200, {"v": "b"}))
    assert cache.get("a") == (200, {"v": "a"})  # touch a -> b is now LRU
    cache.put("c", (200, {"v": "c"}))
    assert cache.get("b") is None
    assert cache.get("a") is not None
    assert len(cache) == 2

    now[0] += 11
    assert cache.get("a") is None
    assert cache.get("c") is None
    assert len(cache) == 0


def _counting_transport(calls: list[dict], status: int = 200, delay: float = 0.0):
    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.read()))
        if delay:
            await asyncio.sleep(delay)
        return httpx.Response(status, json={"completion": "ok", "n": len(calls)})

    return httpx.MockTransport(handler)


def test_forward_caches_2xx_by_payload():
    calls: list[dict] = []
    pool = UpstreamPool(urls=["http://u1:9000"], transport=_counting_transport(calls),
                        ttl_s=60, max_entries=10)

    async def run():
        a = await pool.forward({"prompt": "p", "max_tokens": 64})
        b = await pool.forward({"max_tokens": 64, "prompt": "p"})
        c = await pool.forward({"prompt": "p", "max_tokens": 32})
        await pool.aclose()
        return a, b, c

    a, b, c = asyncio.run(run())
    assert a == b == (200, {"completion": "ok", "n": 1})
    assert c == (200, {"completion": "ok", "n": 2})
    assert len(calls) == 2


def test_forward_does_not_cache_non_2xx():
    calls: list[dict] = []
    pool = UpstreamPool(urls=["http://u1:9000"], transport=_counting_transport(calls, status=503),
                        ttl_s=60, max_entries=10)

    async def run():
        await pool.forward({"prompt": "p"})
        await pool.forward({"prompt": "p"})
        await pool.aclose()

    asyncio.run(run())
    assert len(calls) == 2


def test_forward_coalesces_concurrent_identical_requests():
    calls: list[dict] = []
    pool = UpstreamPool(urls=["http://u1:9000"], transport=_counting_transport(calls, delay=0.05),
                        ttl_s=60, max_entries=10)

    async def run():
        results = await asyncio.gather(*(pool.forward({"prompt": "same"}) for _ in range(20)))
        other = await pool.forward({"prompt": "other"})
        await pool.aclose()
        return results, other

    results, other = asyncio.run(run())
    assert len(calls) == 2
    assert all(r == (200, {"completion": "ok", "n": 1}) for r in results)
    assert other[1]["n"] == 2


def test_forward_expires_after_ttl(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("app.upstream.time.monotonic", lambda: now[0])
    calls: list[dict] = []
    pool = UpstreamPool(urls=["http://u1:9000"], transport=_counting_transport(calls),
                        ttl_s=5, max_entries=10)

    async def run():
        await pool.forward({"prompt": "p"})
        now[0] += 4
        await pool.forward({"prompt": "p"})
        now[0] += 2
        await pool.forward({"prompt": "p"})
        await pool.aclose()

    asyncio.run(run())
    assert len(calls) == 2


def test_cache_disabled_when_ttl_zero():
    calls: list[dict] = []
    pool = UpstreamPool(urls=["http://u1:9000"], transport=_counting_transport(calls),
                        ttl_s=0, max_entries=10)

    async def run():
        await pool.forward({"prompt": "p"})
        await pool.forward({"prompt": "p"})
        await pool.aclose()

    asyncio.run(run())
    assert len(calls) == 2
