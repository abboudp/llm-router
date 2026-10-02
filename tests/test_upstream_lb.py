import asyncio
import random

import httpx
import pytest

from app.upstream import LatencyBalancer, UpstreamPool

URLS = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _origin(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}:{request.url.port}"


def _transport(clock: FakeClock, hits: list[str], latency_ms: dict[str, float],
               status: dict[str, int] | None = None,
               raises: set[str] | None = None) -> httpx.MockTransport:
    status = status or {}
    raises = raises or set()

    async def handler(request: httpx.Request) -> httpx.Response:
        origin = _origin(request)
        hits.append(origin)
        clock.now += latency_ms.get(origin, 0.0) / 1000.0
        if origin in raises:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(status.get(origin, 200), json={"completion": origin})

    return httpx.MockTransport(handler)


def _balancer(clock: FakeClock, urls=URLS, alpha=0.3, threshold=3, cooldown_s=5.0):
    return LatencyBalancer(urls, alpha=alpha, failure_threshold=threshold,
                           cooldown_s=cooldown_s, clock=clock, rng=random.Random(0))


def _run(pool: UpstreamPool, n: int, payload=None):
    async def go():
        out = []
        for _ in range(n):
            out.append(await pool.forward(payload or {"prompt": "p"}))
        await pool.aclose()
        return out

    return asyncio.run(go())


@pytest.fixture
def lb_env(monkeypatch):
    for name in ("ROUTER_LB_EWMA_ALPHA", "ROUTER_LB_FAILURE_THRESHOLD", "ROUTER_LB_COOLDOWN_MS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ROUTER_LB_ENABLED", "1")
    return monkeypatch


def test_flag_off_is_round_robin(monkeypatch):
    monkeypatch.delenv("ROUTER_LB_ENABLED", raising=False)
    clock = FakeClock()
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport(clock, hits, {URLS[0]: 500}),
                        clock=clock)
    assert pool.balancer is None
    _run(pool, 7)
    assert hits == URLS * 2 + URLS[:1]


def test_flag_explicitly_zero_is_round_robin(monkeypatch):
    monkeypatch.setenv("ROUTER_LB_ENABLED", "0")
    assert UpstreamPool(urls=URLS).balancer is None


def test_flag_on_reads_config(lb_env):
    lb_env.setenv("ROUTER_LB_EWMA_ALPHA", "0.5")
    lb_env.setenv("ROUTER_LB_FAILURE_THRESHOLD", "4")
    lb_env.setenv("ROUTER_LB_COOLDOWN_MS", "250")
    lb = UpstreamPool(urls=URLS).balancer
    assert lb is not None
    assert (lb._alpha, lb._threshold, lb._cooldown) == (0.5, 4, 0.25)


def test_invalid_alpha_rejected():
    with pytest.raises(ValueError):
        _balancer(FakeClock(), alpha=0)


def test_ewma_update_math(lb_env):
    lb_env.setenv("ROUTER_LB_EWMA_ALPHA", "0.5")
    clock = FakeClock()
    latencies = iter([100.0, 200.0, 400.0])
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_origin(request))
        clock.now += next(latencies) / 1000.0
        return httpx.Response(200, json={"completion": "ok"})

    pool = UpstreamPool(urls=URLS[:1], transport=httpx.MockTransport(handler), clock=clock)
    backend = pool.balancer.backends[0]
    ewmas = []

    async def go():
        for _ in range(3):
            await pool.forward({"prompt": "p"})
            ewmas.append(backend.ewma)
        await pool.aclose()

    asyncio.run(go())
    # first sample seeds, then ewma = a * x + (1 - a) * ewma
    assert ewmas == pytest.approx([100.0, 150.0, 275.0])
    assert backend.inflight == 0


def test_unknown_backends_sampled_then_lowest_ewma_wins(lb_env):
    clock = FakeClock()
    hits: list[str] = []
    latency = {URLS[0]: 100.0, URLS[1]: 50.0, URLS[2]: 300.0}
    pool = UpstreamPool(urls=URLS, transport=_transport(clock, hits, latency),
                        clock=clock, rng=random.Random(1))
    results = _run(pool, 13)
    assert set(hits[:3]) == set(URLS)
    assert hits[3:] == [URLS[1]] * 10
    assert results[-1] == (200, {"completion": URLS[1]})


def test_selection_tracks_latency_changes(lb_env):
    clock = FakeClock()
    hits: list[str] = []
    latency = {URLS[0]: 50.0, URLS[1]: 100.0}
    pool = UpstreamPool(urls=URLS[:2], transport=_transport(clock, hits, latency),
                        clock=clock, rng=random.Random(0))

    async def go():
        for _ in range(5):
            await pool.forward({})
        latency[URLS[0]] = 1000.0
        for _ in range(10):
            await pool.forward({})
        await pool.aclose()

    asyncio.run(go())
    assert hits[2:5] == [URLS[0]] * 3
    assert hits[-5:] == [URLS[1]] * 5


def test_inflight_spreads_concurrent_load():
    lb = _balancer(FakeClock(), urls=URLS[:2])
    a, b = lb.backends
    a.ewma, b.ewma = 100.0, 120.0
    picks = [lb.acquire()[0].url for _ in range(4)]
    # scores: a=100*1 -> b=120*1 -> a=100*2 -> b=120*2 (< a=100*3)
    assert picks == [URLS[0], URLS[1], URLS[0], URLS[1]]
    assert (a.inflight, b.inflight) == (2, 2)


def test_ties_are_randomized():
    lb = _balancer(FakeClock())
    for b in lb.backends:
        b.ewma = 100.0
    seen = set()
    for _ in range(50):
        b, _probe = lb.acquire()
        lb.record_success(b, 0.1, False)
        seen.add(b.url)
    assert seen == set(URLS)


def test_breaker_opens_after_consecutive_failures():
    clock = FakeClock()
    lb = _balancer(clock, threshold=3)
    bad = lb.backends[0]
    for _ in range(2):
        bad.inflight += 1
        lb.record_failure(bad, False)
    assert bad.opened_at is None
    bad.inflight += 1
    lb.record_success(bad, 0.01, False)
    assert bad.failures == 0
    for _ in range(3):
        bad.inflight += 1
        lb.record_failure(bad, False)
    assert bad.opened_at == 0.0
    bad.ewma = 1.0  # would win on latency if it were selectable
    for _ in range(20):
        b, probe = lb.acquire()
        assert b is not bad and not probe
        lb.record_success(b, 0.1, probe)


def test_half_open_probe_after_cooldown_success_closes():
    clock = FakeClock()
    lb = _balancer(clock, threshold=1, cooldown_s=5.0)
    bad = lb.backends[0]
    bad.inflight += 1
    lb.record_failure(bad, False)
    clock.now = 4.999
    assert all(lb.acquire()[0] is not bad for _ in range(5))
    clock.now = 5.0
    b, probe = lb.acquire()
    assert b is bad and probe
    # only one probe at a time
    assert all(lb.acquire()[0] is not bad for _ in range(5))
    lb.record_success(bad, 0.01, probe)
    assert bad.opened_at is None and not bad.probing and bad.failures == 0


def test_half_open_probe_failure_reopens():
    clock = FakeClock()
    lb = _balancer(clock, threshold=3, cooldown_s=5.0)
    bad = lb.backends[0]
    for _ in range(3):
        bad.inflight += 1
        lb.record_failure(bad, False)
    clock.now = 6.0
    b, probe = lb.acquire()
    assert b is bad and probe
    lb.record_failure(bad, probe)
    assert bad.opened_at == 6.0 and not bad.probing
    clock.now = 10.9
    assert all(lb.acquire()[0] is not bad for _ in range(5))
    clock.now = 11.0
    assert lb.acquire() == (bad, True)


def test_all_broken_falls_back_to_round_robin():
    clock = FakeClock()
    lb = _balancer(clock, threshold=1, cooldown_s=60.0)
    for b in lb.backends:
        b.inflight += 1
        lb.record_failure(b, False)
    picks = [lb.acquire() for _ in range(4)]
    assert [b.url for b, _ in picks] == URLS + URLS[:1]
    assert not any(probe for _, probe in picks)


def test_pool_counts_5xx_and_connect_errors_as_failures(lb_env):
    lb_env.setenv("ROUTER_LB_FAILURE_THRESHOLD", "2")
    lb_env.setenv("ROUTER_LB_COOLDOWN_MS", "1000")
    clock = FakeClock()
    hits: list[str] = []
    transport = _transport(clock, hits, {}, status={URLS[0]: 503}, raises={URLS[1]})
    pool = UpstreamPool(urls=URLS[:2], transport=transport, clock=clock)
    u1, u2 = pool.balancer.backends

    async def go():
        statuses, errors = [], 0
        for _ in range(8):
            try:
                statuses.append((await pool.forward({}))[0])
            except httpx.ConnectError:
                errors += 1
        return statuses, errors

    statuses, errors = asyncio.run(go())
    assert u1.opened_at is not None and u2.opened_at is not None
    assert u1.inflight == u2.inflight == 0
    # 2 failures each opens both breakers, then round-robin fallback
    assert hits[4:] == [URLS[0], URLS[1], URLS[0], URLS[1]]
    assert statuses == [503] * 4 and errors == 4
    assert u1.ewma is None and u2.ewma is None

    clock.now += 1.0
    hits.clear()
    asyncio.run(pool.forward({}))
    assert len(hits) == 1
    asyncio.run(pool.aclose())


def test_pool_recovers_backend_through_probe(lb_env):
    lb_env.setenv("ROUTER_LB_FAILURE_THRESHOLD", "1")
    lb_env.setenv("ROUTER_LB_COOLDOWN_MS", "1000")
    clock = FakeClock()
    hits: list[str] = []
    status = {URLS[0]: 500}
    pool = UpstreamPool(urls=URLS[:2], transport=_transport(clock, hits, {URLS[1]: 10.0}, status),
                        clock=clock, rng=random.Random(0))
    u1, _u2 = pool.balancer.backends

    async def go():
        while u1.opened_at is None:
            await pool.forward({})
        hits.clear()
        for _ in range(3):
            await pool.forward({})
        assert URLS[0] not in hits
        status[URLS[0]] = 200
        clock.now += 1.0
        hits.clear()
        await pool.forward({})
        assert hits == [URLS[0]]
        assert u1.opened_at is None and u1.ewma == 0.0
        await pool.aclose()

    asyncio.run(go())
