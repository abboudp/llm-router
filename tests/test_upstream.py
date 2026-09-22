import asyncio
import random

import httpx

from app.config import (
    upstream_ewma_alpha,
    upstream_hedge_delay_s,
    upstream_timeout_s,
    upstream_urls,
)
from app.upstream import Replica, UpstreamPool

U1, U2, U3 = "http://u1:9000", "http://u2:9000", "http://u3:9000"
URLS = [U1, U2, U3]


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


def test_timeout_and_hedge_config(monkeypatch):
    monkeypatch.delenv("LLM_UPSTREAM_TIMEOUT_S", raising=False)
    monkeypatch.delenv("LLM_UPSTREAM_HEDGE_DELAY_S", raising=False)
    monkeypatch.delenv("LLM_UPSTREAM_EWMA_ALPHA", raising=False)
    assert upstream_timeout_s() == 10.0
    assert upstream_hedge_delay_s() == 0.5
    assert upstream_ewma_alpha() == 0.2
    monkeypatch.setenv("LLM_UPSTREAM_TIMEOUT_S", "2.5")
    monkeypatch.setenv("LLM_UPSTREAM_HEDGE_DELAY_S", "0")
    monkeypatch.setenv("LLM_UPSTREAM_EWMA_ALPHA", "0.5")
    assert upstream_timeout_s() == 2.5
    assert upstream_hedge_delay_s() == 0
    assert upstream_ewma_alpha() == 0.5


def _origin(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}:{request.url.port}"


def _recording_transport(hits: list[str]) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_origin(request))
        return httpx.Response(200, json={"completion": "ok"})

    return httpx.MockTransport(handler)


def _delayed_transport(hits: list[str], delays: dict[str, float],
                       bodies: dict[str, dict] | None = None) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        origin = _origin(request)
        hits.append(origin)
        await asyncio.sleep(delays.get(origin, 0.0))
        return httpx.Response(200, json=(bodies or {}).get(origin, {"completion": "ok"}))

    return httpx.MockTransport(handler)


def _run(coro):
    return asyncio.run(coro)


def test_passthrough_and_every_replica_gets_probed():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_recording_transport(hits), hedge_delay_s=0)

    async def run():
        results = [await pool.forward({"prompt": "p"}) for _ in range(30)]
        await pool.aclose()
        return results

    results = _run(run())
    assert len(hits) == 30  # no hedges fired for instant responses
    assert set(hits) == set(URLS)
    assert all(r == (200, {"completion": "ok"}) for r in results)


def test_pick_is_power_of_two_choices_on_score():
    pool = UpstreamPool(urls=URLS, transport=_recording_transport([]), rng=random.Random(1))
    fast, mid, slow = pool.replicas
    fast.ewma_ms, mid.ewma_ms, slow.ewma_ms = 100, 200, 1300
    picks = [pool.pick().url for _ in range(300)]
    # slow only wins when it is not sampled against a faster peer: never, with 3 replicas
    assert slow.url not in picks
    assert picks.count(fast.url) > picks.count(mid.url)
    # in-flight load can outweigh a small latency edge
    fast.inflight = 5
    assert pool.pick(exclude={slow.url}) is mid
    # exclusion is honored, even down to a single candidate
    assert pool.pick(exclude={fast.url, mid.url}) is slow
    _run(pool.aclose())


def test_ewma_observe():
    r = Replica("http://x:1", _alpha=0.5)
    r.observe(100)
    assert r.ewma_ms == 100
    r.observe(300)
    assert r.ewma_ms == 200
    assert r.score() == 200
    r.inflight = 1
    assert r.score() == 400


def test_uniformly_slow_replica_gets_little_traffic():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_delayed_transport(
        hits, {U1: 0.01, U2: 0.01, U3: 0.08}), hedge_delay_s=0, ewma_alpha=0.2)

    async def run():
        # first few sequential calls probe every replica
        for _ in range(6):
            await pool.forward({"prompt": "p"})
        hits.clear()
        await asyncio.gather(*(pool.forward({"prompt": "p"}) for _ in range(60)))
        await pool.aclose()

    _run(run())
    assert hits.count(U3) < len(hits) * 0.15, hits.count(U3)


def test_hedge_fires_on_a_different_replica_and_first_result_wins():
    hits: list[str] = []
    pool = UpstreamPool(urls=[U1, U2], transport=_delayed_transport(
        hits, {U1: 1.0, U2: 0.01}, bodies={U1: {"completion": "slow"}, U2: {"completion": "fast"}}),
        hedge_delay_s=0.05, rng=random.Random(0))
    pool.replicas[1].ewma_ms = 1.0  # unprobed U1 scores 0, so the first pick lands on it

    async def run():
        t0 = asyncio.get_running_loop().time()
        result = await pool.forward({"prompt": "p"})
        elapsed = asyncio.get_running_loop().time() - t0
        await pool.aclose()
        return result, elapsed

    result, elapsed = _run(run())
    assert hits == [U1, U2]
    assert result == (200, {"completion": "fast"})
    assert elapsed < 0.5
    assert all(r.inflight == 0 for r in pool.replicas)


def test_no_hedge_when_fast_path_returns_in_time():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_delayed_transport(hits, {u: 0.01 for u in URLS}),
                        hedge_delay_s=0.2)
    assert _run(pool.forward({"prompt": "p"})) == (200, {"completion": "ok"})
    assert len(hits) == 1
    _run(pool.aclose())


def test_hedge_disabled_by_zero_delay():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_delayed_transport(hits, {u: 0.1 for u in URLS}),
                        hedge_delay_s=0)
    assert _run(pool.forward({"prompt": "p"})) == (200, {"completion": "ok"})
    assert len(hits) == 1
    _run(pool.aclose())


def test_timeout_retries_once_on_another_replica():
    hits: list[str] = []
    pool = UpstreamPool(urls=[U1, U2], transport=_delayed_transport(hits, {U1: 5.0, U2: 0.0}),
                        timeout_s=0.05, hedge_delay_s=0)
    pool.replicas[1].ewma_ms = 1.0  # unprobed U1 scores 0, so the first pick lands on it

    result = _run(pool.forward({"prompt": "p"}))
    assert hits == [U1, U2]
    assert result == (200, {"completion": "ok"})
    _run(pool.aclose())


def test_all_attempts_failing_returns_502_not_exception():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    pool = UpstreamPool(urls=URLS, transport=httpx.MockTransport(handler), hedge_delay_s=0)
    status, body = _run(pool.forward({"prompt": "p"}))
    assert status == 502
    assert "ConnectError" in body["detail"]
    assert all(r.inflight == 0 for r in pool.replicas)
    _run(pool.aclose())


def test_upstream_error_status_is_passed_through_without_retry():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_origin(request))
        return httpx.Response(400, json={"detail": "bad prompt"})

    pool = UpstreamPool(urls=URLS, transport=httpx.MockTransport(handler), hedge_delay_s=0)
    assert _run(pool.forward({"prompt": "p"})) == (400, {"detail": "bad prompt"})
    assert len(hits) == 1
    _run(pool.aclose())
