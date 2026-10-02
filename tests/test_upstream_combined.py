import asyncio
import random

import httpx
import pytest

from app.upstream import LatencyBalancer, UpstreamPool

URLS = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
FLAG_VARS = ["ROUTER_CACHE_ENABLED", "ROUTER_CACHE_MAX_ENTRIES", "ROUTER_RETRY_ENABLED",
             "ROUTER_HEDGE_ENABLED", "ROUTER_TIMEOUT_MS", "ROUTER_HEDGE_DELAY_MS",
             "ROUTER_MAX_ATTEMPTS", "ROUTER_LB_ENABLED", "ROUTER_LB_EWMA_ALPHA",
             "ROUTER_LB_FAILURE_THRESHOLD", "ROUTER_LB_COOLDOWN_MS"]


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch):
    for name in FLAG_VARS:
        monkeypatch.delenv(name, raising=False)


def _origin(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}:{request.url.port}"


def _transport(hits: list[str], status: dict[str, int] | None = None,
               delay_s: dict[str, float] | None = None) -> httpx.MockTransport:
    status = status or {}
    delay_s = delay_s or {}

    async def handler(request: httpx.Request) -> httpx.Response:
        origin = _origin(request)
        hits.append(origin)
        if origin in delay_s:
            await asyncio.sleep(delay_s[origin])
        return httpx.Response(status.get(origin, 200), json={"completion": origin})

    return httpx.MockTransport(handler)


def _seed(pool: UpstreamPool, ewma: dict[str, float]) -> None:
    assert pool.balancer is not None
    for b in pool.balancer.backends:
        b.ewma = ewma[b.url]


def test_all_flags_off_is_plain_round_robin():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport(hits))
    assert pool.balancer is None and pool._cache is None and not pool._failover

    async def go():
        for _ in range(6):
            await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()

    asyncio.run(go())
    assert hits == URLS * 2


def test_flags_read_independently_from_env(monkeypatch):
    monkeypatch.setenv("ROUTER_CACHE_ENABLED", "1")
    monkeypatch.setenv("ROUTER_LB_ENABLED", "1")
    pool = UpstreamPool(urls=URLS)
    assert pool._cache is not None and pool.balancer is not None and not pool._failover
    monkeypatch.delenv("ROUTER_CACHE_ENABLED")
    monkeypatch.setenv("ROUTER_HEDGE_ENABLED", "1")
    pool = UpstreamPool(urls=URLS)
    assert pool._cache is None and pool.balancer is not None and pool._hedge and not pool._retry


def test_cache_hit_skips_balancer_and_upstream():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport(hits), cache=True, lb=True,
                        retry_enabled=True, hedge_enabled=True, hedge_delay_ms=50,
                        rng=random.Random(0))

    async def go():
        first = await pool.forward({"prompt": "p", "max_tokens": 8})
        second = await pool.forward({"prompt": "p", "max_tokens": 8})
        await pool.aclose()
        return first, second

    first, second = asyncio.run(go())
    assert first == second and first[0] == 200
    assert len(hits) == 1
    assert all(b.inflight == 0 for b in pool.balancer.backends)


def test_retry_uses_balancer_and_skips_failed_backend():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport(hits, status={URLS[0]: 503}),
                        lb=True, retry_enabled=True, rng=random.Random(0))
    _seed(pool, {URLS[0]: 10.0, URLS[1]: 50.0, URLS[2]: 500.0})

    async def go():
        out = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return out

    status, body = asyncio.run(go())
    assert status == 200 and body == {"completion": URLS[1]}
    assert hits == [URLS[0], URLS[1]]
    u1, u2, _ = pool.balancer.backends
    assert u1.failures == 1 and u2.failures == 0
    assert all(b.inflight == 0 for b in pool.balancer.backends)


def test_hedge_goes_to_next_best_backend_and_loser_raises_ewma():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport(hits, delay_s={URLS[0]: 0.5}),
                        lb=True, hedge_enabled=True, hedge_delay_ms=20, rng=random.Random(0))
    _seed(pool, {URLS[0]: 10.0, URLS[1]: 50.0, URLS[2]: 500.0})

    async def go():
        out = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return out

    status, body = asyncio.run(go())
    assert status == 200 and body == {"completion": URLS[1]}
    assert hits == [URLS[0], URLS[1]]
    u1, _, u3 = pool.balancer.backends
    assert u1.ewma > 10.0 and u1.failures == 0
    assert u3.ewma == 500.0
    assert all(b.inflight == 0 for b in pool.balancer.backends)


def test_acquire_excludes_tried_backends_unless_all_excluded():
    lb = LatencyBalancer(URLS, alpha=0.3, failure_threshold=1, cooldown_s=60.0,
                         clock=lambda: 0.0, rng=random.Random(0))
    u1, u2, u3 = lb.backends
    u1.ewma, u2.ewma, u3.ewma = 10.0, 20.0, 30.0
    assert lb.acquire()[0] is u1
    assert lb.acquire(exclude=[u1])[0] is u2
    assert lb.acquire(exclude=[u1, u2, u3])[0] in lb.backends

    for b in lb.backends:
        b.inflight = 0
        b.opened_at = 0.0
    assert lb.acquire(exclude=[u1])[0] is not u1


def test_release_ignores_shorter_abandoned_latency():
    lb = LatencyBalancer(URLS[:1], alpha=0.5, failure_threshold=3, cooldown_s=1.0,
                         clock=lambda: 0.0)
    b = lb.backends[0]
    b.ewma, b.inflight = 100.0, 2
    lb.release(b, probe=False, elapsed_s=0.05)
    assert b.ewma == 100.0
    lb.release(b, probe=False, elapsed_s=0.3)
    assert b.ewma == 200.0 and b.inflight == 0
