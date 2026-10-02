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


URLS = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]


def _host(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}:{request.url.port}"


def test_blocked_request_on_a_sends_next_request_to_b():
    hits: list[str] = []
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_host(request))
        if _host(request) == URLS[0]:
            await release.wait()
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(urls=URLS[:2], transport=httpx.MockTransport(handler))

    async def run():
        blocked = asyncio.create_task(pool.forward({"prompt": "slow"}))
        while hits != [URLS[0]]:
            await asyncio.sleep(0)
        assert pool.in_flight() == {URLS[0]: 1, URLS[1]: 0}
        second = await pool.forward({"prompt": "fast"})
        third = await pool.forward({"prompt": "fast"})
        release.set()
        first = await blocked
        await pool.aclose()
        return first, second, third

    first, second, third = asyncio.run(run())
    # A stays busy, so both concurrent requests go to B
    assert hits == [URLS[0], URLS[1], URLS[1]]
    assert first == second == third == (200, {"completion": "ok"})
    assert pool.in_flight() == {URLS[0]: 0, URLS[1]: 0}


def test_counters_balanced_after_success_and_transport_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        if _host(request) == URLS[1]:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(urls=URLS, transport=httpx.MockTransport(handler))

    async def run():
        outcomes = []
        for _ in range(6):
            try:
                outcomes.append((await pool.forward({"prompt": "p"}))[0])
            except httpx.ConnectError:
                outcomes.append("error")
        await pool.aclose()
        return outcomes

    outcomes = asyncio.run(run())
    assert outcomes == [200, "error", 200, 200, "error", 200]
    assert pool.in_flight() == {url: 0 for url in URLS}


def test_parallel_burst_spreads_across_all_urls():
    hits: list[str] = []
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_host(request))
        await release.wait()
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(urls=URLS, transport=httpx.MockTransport(handler))

    async def run():
        tasks = [asyncio.create_task(pool.forward({"prompt": "p"})) for _ in range(9)]
        while len(hits) < 9:
            await asyncio.sleep(0)
        peak = pool.in_flight()
        release.set()
        results = await asyncio.gather(*tasks)
        await pool.aclose()
        return peak, results

    peak, results = asyncio.run(run())
    assert peak == {url: 3 for url in URLS}
    assert sorted(hits) == sorted(URLS * 3)
    assert all(r[0] == 200 for r in results)
    assert pool.in_flight() == {url: 0 for url in URLS}


def test_tie_breaking_is_deterministic_round_robin():
    def run_once() -> list[str]:
        hits: list[str] = []
        pool = UpstreamPool(urls=URLS, transport=_recording_transport(hits))

        async def run():
            for _ in range(7):
                await pool.forward({"prompt": "p"})
            await pool.aclose()

        asyncio.run(run())
        return hits

    first = run_once()
    assert first == [URLS[i % 3] for i in range(7)]
    assert run_once() == first
