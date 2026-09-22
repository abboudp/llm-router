import asyncio

import httpx

from app.upstream import ReplicaStats, UpstreamPool

FAST, SLOW = "http://fast:9000", "http://slow:9000"


def _transport(delays: dict[str, float], hits: list[str], fail: set[str] = frozenset()):
    async def handler(request: httpx.Request) -> httpx.Response:
        host = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        hits.append(host)
        await asyncio.sleep(delays.get(host, 0))
        if host in fail:
            return httpx.Response(503, json={"detail": "overloaded"})
        return httpx.Response(200, json={"completion": "ok", "from": host})

    return httpx.MockTransport(handler)


def _run(coro):
    return asyncio.run(coro)


def test_hedge_fires_after_delay_and_fastest_wins():
    hits: list[str] = []
    pool = UpstreamPool(urls=[SLOW, FAST], hedge_delays_ms=(20,),
                        transport=_transport({SLOW: 0.5}, hits))

    async def run():
        t0 = asyncio.get_event_loop().time()
        res = await pool.forward({"prompt": "p"})
        elapsed = asyncio.get_event_loop().time() - t0
        await pool.aclose()
        return res, elapsed

    (status, body), elapsed = _run(run())
    assert status == 200 and body["from"] == FAST
    assert hits == [SLOW, FAST]
    assert elapsed < 0.3
    assert pool.hedged == 1 and pool.hedge_wins == 1


def test_no_hedge_when_primary_is_fast():
    hits: list[str] = []
    pool = UpstreamPool(urls=[FAST, SLOW], hedge_delays_ms=(50,),
                        transport=_transport({}, hits))

    async def run():
        res = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return res

    status, body = _run(run())
    assert status == 200 and body["from"] == FAST
    assert hits == [FAST]
    assert pool.hedged == 0


def test_consistently_slow_replica_is_skipped_as_primary():
    hits: list[str] = []
    pool = UpstreamPool(urls=[FAST, SLOW], hedge_delays_ms=(1000,),
                        transport=_transport({SLOW: 0.05}, hits))

    async def run():
        # warm-up: round-robin visits both so the slow one gets an EWMA
        for _ in range(2):
            await pool.forward({"prompt": "p"})
        hits.clear()
        for _ in range(4):
            await pool.forward({"prompt": "p"})
        await pool.aclose()

    _run(run())
    assert hits == [FAST] * 4


def test_5xx_falls_through_to_next_replica():
    hits: list[str] = []
    bad = "http://bad:9000"
    pool = UpstreamPool(urls=[bad, FAST], hedge_delays_ms=(1000,),
                        transport=_transport({}, hits, fail={bad}))

    async def run():
        res = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return res

    status, body = _run(run())
    assert status == 200 and body["from"] == FAST
    assert hits == [bad, FAST]


def test_all_5xx_returns_last_error_status():
    hits: list[str] = []
    a, b = "http://a:9000", "http://b:9000"
    pool = UpstreamPool(urls=[a, b], hedge_delays_ms=(1000,),
                        transport=_transport({}, hits, fail={a, b}))

    async def run():
        res = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return res

    status, body = _run(run())
    assert status == 503 and body == {"detail": "overloaded"}


def test_censored_sample_never_lowers_ewma():
    s = ReplicaStats()
    s.record(1000)
    s.record(100, censored=True)
    assert s.ewma_ms == 1000
    s.record(2000, censored=True)
    assert s.ewma_ms > 1000
