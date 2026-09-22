import asyncio
import time

import httpx

from app.config import (
    cache_max,
    cache_ttl_s,
    hedge_delay_ms,
    slow_delta_ms,
    upstream_urls,
)
from app.upstream import UpstreamPool


def test_upstream_urls_default(monkeypatch):
    monkeypatch.delenv("LLM_SERVICE_URLS", raising=False)
    assert upstream_urls() == [
        "http://localhost:9001",
        "http://localhost:9002",
        "http://localhost:9003",
    ]


def test_upstream_urls_env(monkeypatch):
    monkeypatch.setenv("LLM_SERVICE_URLS", "http://a:1, http://b:2")
    assert upstream_urls() == ["http://a:1", "http://b:2"]


def test_upstream_latency_config_defaults(monkeypatch):
    for name in (
        "LLM_HEDGE_DELAY_MS",
        "LLM_SLOW_DELTA_MS",
        "LLM_CACHE_TTL_S",
        "LLM_CACHE_MAX",
    ):
        monkeypatch.delenv(name, raising=False)
    assert hedge_delay_ms() == 300
    assert slow_delta_ms() == 250
    assert cache_ttl_s() == 300
    assert cache_max() == 2048


def test_upstream_latency_config_env(monkeypatch):
    monkeypatch.setenv("LLM_HEDGE_DELAY_MS", "17")
    monkeypatch.setenv("LLM_SLOW_DELTA_MS", "23")
    monkeypatch.setenv("LLM_CACHE_TTL_S", "41")
    monkeypatch.setenv("LLM_CACHE_MAX", "59")
    assert hedge_delay_ms() == 17
    assert slow_delta_ms() == 23
    assert cache_ttl_s() == 41
    assert cache_max() == 59


def _recording_transport(hits: list[str]) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(f"{request.url.scheme}://{request.url.host}:{request.url.port}")
        return httpx.Response(200, json={"completion": "ok"})

    return httpx.MockTransport(handler)


def test_round_robin_and_passthrough():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    pool = UpstreamPool(urls=urls, transport=_recording_transport(hits))

    async def run():
        results = [await pool.forward({"prompt": "p"}) for _ in range(4)]
        await pool.aclose()
        return results

    results = asyncio.run(run())
    assert hits == ["http://u1:9000", "http://u2:9000", "http://u3:9000", "http://u1:9000"]
    assert all(r == (200, {"completion": "ok"}) for r in results)


def test_hedge_wins_over_stalled_primary():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        if request.url.host == "u1":
            await asyncio.sleep(1.0)
        return httpx.Response(200, json={"completion": request.url.host})

    pool = UpstreamPool(
        urls=["http://u1:9000", "http://u2:9000"],
        transport=httpx.MockTransport(handler),
        hedge_delay_ms=50,
        cache_ttl_s=0,
    )

    async def run():
        started = time.perf_counter()
        result = await pool.forward({"prompt": "p", "max_tokens": 1})
        elapsed = time.perf_counter() - started
        await pool.aclose()
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert result == (200, {"completion": "u2"})
    assert elapsed < 0.5
    assert hits == ["u1", "u2"]


def test_no_hedge_when_primary_is_fast():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        return httpx.Response(200, json={"completion": request.url.host})

    pool = UpstreamPool(
        urls=["http://u1:9000", "http://u2:9000"],
        transport=httpx.MockTransport(handler),
        hedge_delay_ms=50,
        cache_ttl_s=0,
    )

    async def run():
        results = [
            await pool.forward({"prompt": f"p-{index}", "max_tokens": 1})
            for index in range(3)
        ]
        await pool.aclose()
        return results

    results = asyncio.run(run())
    assert len(hits) == 3
    assert all(status == 200 for status, _ in results)


def test_degraded_replica_is_deprioritized():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        if request.url.host == "u1":
            await asyncio.sleep(0.4)
        return httpx.Response(200, json={"completion": request.url.host})

    pool = UpstreamPool(
        urls=["http://u1:9000", "http://u2:9000", "http://u3:9000"],
        transport=httpx.MockTransport(handler),
        hedge_delay_ms=10_000,
        slow_delta_ms=100,
        cache_ttl_s=0,
    )

    async def run():
        elapsed: list[float] = []
        for index in range(12):
            started = time.perf_counter()
            await pool.forward({"prompt": f"p-{index}", "max_tokens": 1})
            elapsed.append(time.perf_counter() - started)
        await pool.aclose()
        return elapsed

    elapsed = asyncio.run(run())
    assert hits.count("u1") <= 2
    assert all(duration < 0.2 for duration in elapsed[-6:])


def test_transport_error_fails_over_immediately():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        if request.url.host == "u1":
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"completion": "u2"})

    pool = UpstreamPool(
        urls=["http://u1:9000", "http://u2:9000"],
        transport=httpx.MockTransport(handler),
        hedge_delay_ms=10_000,
        cache_ttl_s=0,
    )

    async def run():
        started = time.perf_counter()
        result = await pool.forward({"prompt": "p", "max_tokens": 1})
        elapsed = time.perf_counter() - started
        await pool.aclose()
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert result == (200, {"completion": "u2"})
    assert elapsed < 0.2
    assert hits == ["u1", "u2"]


def test_5xx_fails_over():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "u1":
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"completion": "u2"})

    pool = UpstreamPool(
        urls=["http://u1:9000", "http://u2:9000"],
        transport=httpx.MockTransport(handler),
        cache_ttl_s=0,
    )

    async def run():
        result = await pool.forward({"prompt": "p", "max_tokens": 1})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (200, {"completion": "u2"})


def test_all_5xx_returns_last_status():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": request.url.host})

    pool = UpstreamPool(
        urls=["http://u1:9000", "http://u2:9000"],
        transport=httpx.MockTransport(handler),
        cache_ttl_s=0,
    )

    async def run():
        result = await pool.forward({"prompt": "p", "max_tokens": 1})
        await pool.aclose()
        return result

    status, _ = asyncio.run(run())
    assert status == 503


def test_cache_hit_skips_upstream():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        return httpx.Response(200, json={"completion": request.content.decode()})

    pool = UpstreamPool(
        urls=["http://u1:9000"],
        transport=httpx.MockTransport(handler),
        cache_ttl_s=300,
    )

    async def run():
        first = await pool.forward({"prompt": "p", "max_tokens": 1})
        second = await pool.forward({"prompt": "p", "max_tokens": 1})
        third = await pool.forward({"prompt": "p", "max_tokens": 2})
        await pool.aclose()
        return first, second, third

    first, second, _ = asyncio.run(run())
    assert len(hits) == 2
    assert first == second


def test_single_flight_coalesces_concurrent_duplicates():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(
        urls=["http://u1:9000"],
        transport=httpx.MockTransport(handler),
        cache_ttl_s=0,
    )

    async def run():
        results = await asyncio.gather(
            *(
                pool.forward({"prompt": "p", "max_tokens": 1})
                for _ in range(5)
            )
        )
        await pool.aclose()
        return results

    results = asyncio.run(run())
    assert len(hits) == 1
    assert results == [(200, {"completion": "ok"})] * 5


def test_cache_does_not_store_errors():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        return httpx.Response(500, json={"error": "nope"})

    pool = UpstreamPool(
        urls=["http://u1:9000"],
        transport=httpx.MockTransport(handler),
        cache_ttl_s=300,
    )

    async def run():
        first = await pool.forward({"prompt": "p", "max_tokens": 1})
        second = await pool.forward({"prompt": "p", "max_tokens": 1})
        await pool.aclose()
        return first, second

    first, second = asyncio.run(run())
    assert first == second == (500, {"error": "nope"})
    assert len(hits) == 2


def test_cache_lru_eviction():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.host)
        return httpx.Response(200, json={"completion": request.content.decode()})

    pool = UpstreamPool(
        urls=["http://u1:9000"],
        transport=httpx.MockTransport(handler),
        cache_ttl_s=300,
        cache_max=2,
    )

    async def run():
        await pool.forward({"prompt": "p1", "max_tokens": 1})
        await pool.forward({"prompt": "p2", "max_tokens": 1})
        await pool.forward({"prompt": "p3", "max_tokens": 1})
        await pool.forward({"prompt": "p1", "max_tokens": 1})
        await pool.aclose()

    asyncio.run(run())
    assert len(hits) == 4
