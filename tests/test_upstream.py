import asyncio

import httpx

from app.config import upstream_urls
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


def _recording_transport(hits: list[str]) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(f"{request.url.scheme}://{request.url.host}:{request.url.port}")
        return httpx.Response(200, json={"completion": "ok"})

    return httpx.MockTransport(handler)


def test_probes_all_replicas_first_and_passes_through():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    pool = UpstreamPool(urls=urls, transport=_recording_transport(hits))

    async def run():
        results = [await pool.forward({"prompt": "p"}) for _ in range(4)]
        await pool.aclose()
        return results

    results = asyncio.run(run())
    assert hits[:3] == ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    assert results == [(200, {"completion": "ok"})] * 4


def test_avoids_slow_replica():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def handler(request: httpx.Request) -> httpx.Response:
        url = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        hits.append(url)
        if url == "http://u3:9000":
            await asyncio.sleep(0.3)
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(
        urls=urls, transport=httpx.MockTransport(handler), hedge_after=1.0
    )

    async def run():
        for _ in range(23):
            assert await pool.forward({"prompt": "p"}) == (
                200, {"completion": "ok"}
            )
        await pool.aclose()

    asyncio.run(run())
    assert hits.count("http://u3:9000") <= 2


def test_hedges_stalled_primary():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def handler(request: httpx.Request) -> httpx.Response:
        url = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        hits.append(url)
        if url == "http://u1:9000":
            await asyncio.sleep(2)
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(
        urls=urls, transport=httpx.MockTransport(handler), hedge_after=0.05
    )

    async def run():
        started = asyncio.get_running_loop().time()
        result = await pool.forward({"prompt": "p"})
        elapsed = asyncio.get_running_loop().time() - started
        await pool.aclose()
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert result == (200, {"completion": "ok"})
    assert elapsed < 1
    assert "http://u2:9000" in hits


def test_non_2xx_primary_waits_for_hedge_success():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def handler(request: httpx.Request) -> httpx.Response:
        url = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        hits.append(url)
        if url == "http://u2:9000":
            await asyncio.sleep(0.1)
            return httpx.Response(200, json={"completion": "ok"})
        return httpx.Response(500, json={"error": "failed"})

    pool = UpstreamPool(
        urls=urls, transport=httpx.MockTransport(handler), hedge_after=0.01
    )

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (200, {"completion": "ok"})


def test_hedge_wraps_to_fast_replica_and_skips_slow_one():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    first_u1_request = True

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal first_u1_request
        url = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        hits.append(url)
        if url == "http://u2:9000" or (
            url == "http://u1:9000" and first_u1_request
        ):
            if url == "http://u1:9000":
                first_u1_request = False
            await asyncio.sleep(2)
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(
        urls=urls,
        transport=httpx.MockTransport(handler),
        hedge_after=0.05,
        max_hedges=2,
    )
    pool._replicas[2].ewma_ms = 5000.0

    async def run():
        started = asyncio.get_running_loop().time()
        result = await pool.forward({"prompt": "p"})
        elapsed = asyncio.get_running_loop().time() - started
        await pool.aclose()
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert result == (200, {"completion": "ok"})
    assert elapsed < 1
    assert "http://u3:9000" not in hits


def test_fast_failure_hedges_immediately():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def handler(request: httpx.Request) -> httpx.Response:
        url = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        hits.append(url)
        if url == "http://u1:9000":
            return httpx.Response(500, json={"error": "failed"})
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(
        urls=urls,
        transport=httpx.MockTransport(handler),
        hedge_after=1.0,
    )

    async def run():
        started = asyncio.get_running_loop().time()
        result = await pool.forward({"prompt": "p"})
        elapsed = asyncio.get_running_loop().time() - started
        await pool.aclose()
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert result == (200, {"completion": "ok"})
    assert elapsed < 0.5
    assert hits[:2] == ["http://u1:9000", "http://u2:9000"]


def test_all_fail_returns_error_not_exception():
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed", request=request)

    pool = UpstreamPool(
        urls=urls,
        transport=httpx.MockTransport(handler),
        hedge_after=0.01,
        max_hedges=2,
    )

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (502, {"error": "upstream unavailable"})
