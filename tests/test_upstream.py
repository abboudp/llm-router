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


def _latency_transport(hits: list[str], delays: dict[str, float],
                       status: dict[str, int] | None = None) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        hits.append(host)
        await asyncio.sleep(delays.get(host, 0))
        return httpx.Response((status or {}).get(host, 200),
                              json={"completion": "ok", "from": host})

    return httpx.MockTransport(handler)


def test_hedge_config_defaults_and_env(monkeypatch):
    from app.config import hedge_delay_s, hedge_fast_set, hedge_max

    for name in ("LLM_HEDGE_DELAY_MS", "LLM_HEDGE_MAX", "LLM_HEDGE_FAST_SET"):
        monkeypatch.delenv(name, raising=False)
    assert hedge_delay_s() == 0.15
    assert hedge_max() == 2
    assert hedge_fast_set() == 2
    monkeypatch.setenv("LLM_HEDGE_DELAY_MS", "100")
    monkeypatch.setenv("LLM_HEDGE_MAX", "1")
    monkeypatch.setenv("LLM_HEDGE_FAST_SET", "0")
    assert hedge_delay_s() == 0.1
    assert hedge_max() == 1
    assert hedge_fast_set() == 0


def test_no_hedge_when_primary_is_fast():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    pool = UpstreamPool(urls=urls, transport=_latency_transport(hits, {"u1": 0.01}),
                        hedge_delay=0.2, max_hedges=2)

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (200, {"completion": "ok", "from": "u1"})
    assert hits == ["u1"]
    assert pool.hedges_sent == 0


def test_hedge_fires_after_delay_and_fast_replica_wins():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    pool = UpstreamPool(urls=urls, transport=_latency_transport(hits, {"u1": 5.0, "u2": 0.01}),
                        hedge_delay=0.05, max_hedges=2)

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (200, {"completion": "ok", "from": "u2"})
    assert hits == ["u1", "u2"]
    assert pool.requests_sent == 2 and pool.hedges_sent == 1


def test_hedges_are_capped():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    delays = {"u1": 0.3, "u2": 5.0, "u3": 5.0}
    pool = UpstreamPool(urls=urls, transport=_latency_transport(hits, delays),
                        hedge_delay=0.02, max_hedges=1)

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (200, {"completion": "ok", "from": "u1"})
    assert hits == ["u1", "u2"]
    assert pool.hedges_sent == 1


def test_non_2xx_from_hedge_does_not_win():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000"]
    pool = UpstreamPool(urls=urls,
                        transport=_latency_transport(hits, {"u1": 0.2, "u2": 0.01},
                                                     status={"u2": 503}),
                        hedge_delay=0.02, max_hedges=1)

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (200, {"completion": "ok", "from": "u1"})


def test_all_non_2xx_returns_last_status():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000"]
    pool = UpstreamPool(urls=urls,
                        transport=_latency_transport(hits, {}, status={"u1": 500, "u2": 503}),
                        hedge_delay=0.02, max_hedges=1)

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    status, body = asyncio.run(run())
    assert status in (500, 503)
    assert hits == ["u1", "u2"]


def test_round_robin_advances_by_one_per_request_with_hedging():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    pool = UpstreamPool(urls=urls, transport=_latency_transport(hits, {}),
                        hedge_delay=0.2, max_hedges=2)

    async def run():
        for _ in range(3):
            await pool.forward({"prompt": "p"})
        await pool.aclose()

    asyncio.run(run())
    assert hits == ["u1", "u2", "u3"]


def test_hedges_prefer_fastest_upstreams_and_may_repeat_them():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    pool = UpstreamPool(urls=urls, transport=_latency_transport(hits, {"u1": 0.01, "u2": 0.02, "u3": 1.0}),
                        hedge_delay=0.05, max_hedges=2, fast_set=2)

    async def run():
        # warm up the latency ranking: u3 is consistently slow
        for _ in range(3):
            await pool.forward({"prompt": "warm"})
        hits.clear()
        assert pool._candidates() == ["http://u1:9000", "http://u2:9000", "http://u1:9000"]
        assert pool._candidates() == ["http://u2:9000", "http://u1:9000", "http://u2:9000"]
        assert pool._candidates() == ["http://u3:9000", "http://u1:9000", "http://u2:9000"]
        await pool.aclose()

    asyncio.run(run())


def test_fast_set_zero_hedges_in_round_robin_order():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    pool = UpstreamPool(urls=urls, transport=_latency_transport(hits, {}),
                        hedge_delay=0.05, max_hedges=2, fast_set=0)
    assert pool._candidates() == ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    assert pool._candidates() == ["http://u2:9000", "http://u3:9000", "http://u1:9000"]
    asyncio.run(pool.aclose())


def test_max_hedges_zero_is_plain_round_robin():
    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000"]
    pool = UpstreamPool(urls=urls, transport=_latency_transport(hits, {"u1": 0.1}),
                        hedge_delay=0.01, max_hedges=0)
    asyncio.run(pool.forward({"prompt": "p"}))
    asyncio.run(pool.aclose())
    assert hits == ["u1"] and pool.hedges_sent == 0
