import asyncio
import json

import httpx

from app.config import cache_enabled, cache_max_entries
from app.upstream import UpstreamPool


def _transport(calls: list[dict], status: int = 200, delay: float = 0.0,
               statuses: list[int] | None = None) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if delay:
            await asyncio.sleep(delay)
        code = statuses.pop(0) if statuses else status
        if code != 200:
            return httpx.Response(code, json={"detail": "boom"})
        return httpx.Response(200, json={
            "completion": f"{payload['prompt']}:{payload['max_tokens']}",
            "signature": "a" * 64,
            "usage": {"completion_tokens": payload["max_tokens"]},
        })

    return httpx.MockTransport(handler)


def _pool(calls, size=1024, cache=True, **kw) -> UpstreamPool:
    return UpstreamPool(urls=["http://u1:9000", "http://u2:9000"],
                        transport=_transport(calls, **kw), cache=cache, cache_size=size)


def _run(coro):
    return asyncio.run(coro)


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("ROUTER_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("ROUTER_CACHE_MAX_ENTRIES", raising=False)
    assert cache_enabled() is False
    assert cache_max_entries() == 1024


def test_config_env(monkeypatch):
    monkeypatch.setenv("ROUTER_CACHE_ENABLED", "1")
    monkeypatch.setenv("ROUTER_CACHE_MAX_ENTRIES", "7")
    assert cache_enabled() is True
    assert cache_max_entries() == 7
    monkeypatch.setenv("ROUTER_CACHE_ENABLED", "false")
    monkeypatch.setenv("ROUTER_CACHE_MAX_ENTRIES", "nope")
    assert cache_enabled() is False
    assert cache_max_entries() == 1024


def test_pool_reads_env_flags(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setenv("ROUTER_CACHE_ENABLED", "true")
    pool = UpstreamPool(urls=["http://u1:9000"], transport=_transport(calls))

    async def run():
        await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()

    _run(run())
    assert len(calls) == 1


def test_miss_calls_upstream_then_hit_avoids_it():
    calls: list[dict] = []
    pool = _pool(calls)

    async def run():
        first = await pool.forward({"prompt": "p", "max_tokens": 8})
        second = await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()
        return first, second

    first, second = _run(run())
    assert len(calls) == 1
    assert first == second == (200, {
        "completion": "p:8", "signature": "a" * 64, "usage": {"completion_tokens": 8},
    })


def test_returned_bodies_are_copies():
    calls: list[dict] = []
    pool = _pool(calls)

    async def run():
        _, first = await pool.forward({"prompt": "p", "max_tokens": 8})
        first["completion"] = "mutated"
        first["usage"]["completion_tokens"] = -1
        _, second = await pool.forward({"prompt": "p", "max_tokens": 8})
        second["usage"]["completion_tokens"] = -2
        _, third = await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()
        return third

    third = _run(run())
    assert third["completion"] == "p:8"
    assert third["usage"] == {"completion_tokens": 8}


def test_non_200_not_cached():
    calls: list[dict] = []
    pool = _pool(calls, statuses=[503, 500, 200])

    async def run():
        r1 = await pool.forward({"prompt": "p", "max_tokens": 8})
        r2 = await pool.forward({"prompt": "p", "max_tokens": 8})
        r3 = await pool.forward({"prompt": "p", "max_tokens": 8})
        r4 = await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()
        return r1, r2, r3, r4

    r1, r2, r3, r4 = _run(run())
    assert (r1[0], r2[0], r3[0], r4[0]) == (503, 500, 200, 200)
    assert r1[1] == {"detail": "boom"}
    assert len(calls) == 3


def test_lru_eviction_at_bound():
    calls: list[dict] = []
    pool = _pool(calls, size=2)

    async def run():
        for p in ("a", "b"):
            await pool.forward({"prompt": p, "max_tokens": 8})
        await pool.forward({"prompt": "a", "max_tokens": 8})  # hit, refreshes "a"
        await pool.forward({"prompt": "c", "max_tokens": 8})  # evicts "b"
        assert len(pool._cache) == 2
        await pool.forward({"prompt": "a", "max_tokens": 8})  # still cached
        await pool.forward({"prompt": "c", "max_tokens": 8})  # still cached
        await pool.forward({"prompt": "b", "max_tokens": 8})  # evicted -> upstream
        await pool.aclose()

    _run(run())
    assert [c["prompt"] for c in calls] == ["a", "b", "c", "b"]


def test_distinct_max_tokens_are_distinct_keys():
    calls: list[dict] = []
    pool = _pool(calls)

    async def run():
        a = await pool.forward({"prompt": "p", "max_tokens": 8})
        b = await pool.forward({"prompt": "p", "max_tokens": 16})
        a2 = await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()
        return a, b, a2

    a, b, a2 = _run(run())
    assert len(calls) == 2
    assert a[1]["completion"] == "p:8" == a2[1]["completion"]
    assert b[1]["completion"] == "p:16"


def test_flag_off_no_caching():
    calls: list[dict] = []
    pool = _pool(calls, cache=False)

    async def run():
        for _ in range(3):
            await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()

    _run(run())
    assert len(calls) == 3
    assert pool._cache is None


def test_zero_size_disables_cache():
    calls: list[dict] = []
    pool = _pool(calls, size=0)

    async def run():
        for _ in range(2):
            await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()

    _run(run())
    assert len(calls) == 2


def test_concurrent_identical_requests_coalesce():
    calls: list[dict] = []
    pool = _pool(calls, delay=0.05)

    async def run():
        results = await asyncio.gather(
            *[pool.forward({"prompt": "p", "max_tokens": 8}) for _ in range(10)],
            pool.forward({"prompt": "q", "max_tokens": 8}),
        )
        await pool.aclose()
        return results

    results = _run(run())
    assert sorted(c["prompt"] for c in calls) == ["p", "q"]
    assert all(r == results[0] for r in results[:10])
    assert results[10][1]["completion"] == "q:8"
    bodies = [r[1] for r in results[:10]]
    assert len({id(b) for b in bodies}) == 10
    assert not pool._cache.inflight


def test_concurrent_followers_retry_independently_when_leader_fails():
    calls: list[dict] = []
    pool = _pool(calls, delay=0.05, statuses=[503, 200, 200, 200])

    async def run():
        results = await asyncio.gather(
            *[pool.forward({"prompt": "p", "max_tokens": 8}) for _ in range(4)]
        )
        await pool.aclose()
        return results

    results = _run(run())
    assert [r[0] for r in results] == [503, 200, 200, 200]
    assert len(calls) == 4
    assert len(pool._cache) == 1


def test_cancelled_follower_does_not_break_leader():
    calls: list[dict] = []
    pool = _pool(calls, delay=0.05)

    async def run():
        leader = asyncio.create_task(pool.forward({"prompt": "p", "max_tokens": 8}))
        await asyncio.sleep(0)
        follower = asyncio.create_task(pool.forward({"prompt": "p", "max_tokens": 8}))
        await asyncio.sleep(0.01)
        follower.cancel()
        result = await leader
        await pool.aclose()
        return result, follower.cancelled()

    result, cancelled = _run(run())
    assert result[0] == 200
    assert cancelled
    assert len(calls) == 1
