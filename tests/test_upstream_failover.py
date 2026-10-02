import asyncio
import time

import httpx
import pytest

from app.config import (
    router_hedge_delay_ms,
    router_hedge_enabled,
    router_max_attempts,
    router_retry_enabled,
    router_timeout_ms,
)
from app.upstream import UpstreamPool

URLS = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
FLAG_VARS = ["ROUTER_RETRY_ENABLED", "ROUTER_HEDGE_ENABLED", "ROUTER_TIMEOUT_MS",
             "ROUTER_HEDGE_DELAY_MS", "ROUTER_MAX_ATTEMPTS"]


@pytest.fixture(autouse=True)
def _clear_flags(monkeypatch):
    for name in FLAG_VARS:
        monkeypatch.delenv(name, raising=False)


def _host(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}:{request.url.port}"


def _transport(behaviours: dict, hits: list[str], cancelled: list[str] | None = None):
    """behaviours maps backend url -> 'ok' | 'slow' | 'hang' | '5xx' | '4xx' | 'conn' | 'timeout'."""

    async def handler(request: httpx.Request) -> httpx.Response:
        host = _host(request)
        hits.append(host)
        mode = behaviours.get(host, "ok")
        try:
            if mode == "slow":
                await asyncio.sleep(0.15)
            elif mode == "hang":
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            if cancelled is not None:
                cancelled.append(host)
            raise
        if mode == "5xx":
            return httpx.Response(503, json={"detail": f"overloaded {host}"})
        if mode == "4xx":
            return httpx.Response(422, json={"detail": "bad request"})
        if mode == "conn":
            raise httpx.ConnectError("connection refused", request=request)
        if mode == "timeout":
            raise httpx.ReadTimeout("read timed out", request=request)
        return httpx.Response(200, json={"completion": f"from {host}"})

    return httpx.MockTransport(handler)


def _run(pool: UpstreamPool, n: int = 1) -> list[tuple[int, dict]]:
    async def go():
        try:
            return [await pool.forward({"prompt": "p"}) for _ in range(n)]
        finally:
            await pool.aclose()

    return asyncio.run(go())


def test_config_defaults():
    assert router_retry_enabled() is False
    assert router_hedge_enabled() is False
    assert router_timeout_ms() == 1000
    assert router_hedge_delay_ms() == 250
    assert router_max_attempts() == 2


def test_config_env(monkeypatch):
    monkeypatch.setenv("ROUTER_RETRY_ENABLED", "1")
    monkeypatch.setenv("ROUTER_HEDGE_ENABLED", "true")
    monkeypatch.setenv("ROUTER_TIMEOUT_MS", "750")
    monkeypatch.setenv("ROUTER_HEDGE_DELAY_MS", "120")
    monkeypatch.setenv("ROUTER_MAX_ATTEMPTS", "3")
    assert router_retry_enabled() is True
    assert router_hedge_enabled() is True
    assert router_timeout_ms() == 750
    assert router_hedge_delay_ms() == 120
    assert router_max_attempts() == 3


def test_flags_off_is_plain_round_robin_without_retry():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "5xx"}, hits))
    results = _run(pool, n=4)
    assert hits == [URLS[0], URLS[1], URLS[2], URLS[0]]
    assert results[0] == (503, {"detail": f"overloaded {URLS[0]}"})
    assert results[1] == (200, {"completion": f"from {URLS[1]}"})


def test_flags_off_keeps_unbounded_timeout():
    pool = UpstreamPool(urls=URLS, transport=_transport({}, []))
    assert pool._client.timeout == httpx.Timeout(None)
    asyncio.run(pool.aclose())


def test_flags_on_uses_bounded_timeout():
    pool = UpstreamPool(urls=URLS, transport=_transport({}, []), retry_enabled=True,
                        timeout_ms=800)
    assert pool._client.timeout == httpx.Timeout(0.8)
    asyncio.run(pool.aclose())


def test_retry_flag_read_from_env(monkeypatch):
    monkeypatch.setenv("ROUTER_RETRY_ENABLED", "1")
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "5xx"}, hits))
    assert _run(pool) == [(200, {"completion": f"from {URLS[1]}"})]
    assert hits == [URLS[0], URLS[1]]


def test_timeout_triggers_retry_on_another_backend():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "hang"}, hits),
                        retry_enabled=True, timeout_ms=50)
    start = time.monotonic()
    assert _run(pool) == [(200, {"completion": f"from {URLS[1]}"})]
    assert time.monotonic() - start < 1
    assert hits == [URLS[0], URLS[1]]


def test_httpx_timeout_error_triggers_retry():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "timeout"}, hits),
                        retry_enabled=True)
    assert _run(pool) == [(200, {"completion": f"from {URLS[1]}"})]
    assert hits == [URLS[0], URLS[1]]


def test_5xx_triggers_retry_on_another_backend():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "5xx"}, hits),
                        retry_enabled=True)
    assert _run(pool) == [(200, {"completion": f"from {URLS[1]}"})]
    assert hits == [URLS[0], URLS[1]]


def test_connection_error_triggers_retry_on_another_backend():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "conn"}, hits),
                        retry_enabled=True)
    assert _run(pool) == [(200, {"completion": f"from {URLS[1]}"})]
    assert hits == [URLS[0], URLS[1]]


def test_4xx_is_not_retried():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "4xx"}, hits),
                        retry_enabled=True)
    assert _run(pool) == [(422, {"detail": "bad request"})]
    assert hits == [URLS[0]]


def test_max_attempts_respected_and_last_5xx_passed_through():
    hits: list[str] = []
    behaviours = {u: "5xx" for u in URLS}
    pool = UpstreamPool(urls=URLS, transport=_transport(behaviours, hits), retry_enabled=True)
    assert _run(pool) == [(503, {"detail": f"overloaded {URLS[1]}"})]
    assert hits == [URLS[0], URLS[1]]


def test_max_attempts_configurable():
    hits: list[str] = []
    behaviours = {URLS[0]: "5xx", URLS[1]: "conn"}
    pool = UpstreamPool(urls=URLS, transport=_transport(behaviours, hits), retry_enabled=True,
                        max_attempts=3)
    assert _run(pool) == [(200, {"completion": f"from {URLS[2]}"})]
    assert hits == URLS


def test_max_attempts_capped_by_backend_count():
    hits: list[str] = []
    behaviours = {u: "5xx" for u in URLS}
    pool = UpstreamPool(urls=URLS, transport=_transport(behaviours, hits), retry_enabled=True,
                        max_attempts=10)
    assert _run(pool)[0][0] == 503
    assert hits == URLS


def test_all_attempts_time_out_returns_504():
    hits: list[str] = []
    behaviours = {u: "hang" for u in URLS}
    pool = UpstreamPool(urls=URLS, transport=_transport(behaviours, hits), retry_enabled=True,
                        timeout_ms=30)
    assert _run(pool) == [(504, {"detail": "upstream timeout"})]
    assert hits == [URLS[0], URLS[1]]


def test_all_attempts_connection_errors_return_502():
    hits: list[str] = []
    behaviours = {u: "conn" for u in URLS}
    pool = UpstreamPool(urls=URLS, transport=_transport(behaviours, hits), retry_enabled=True)
    assert _run(pool) == [(502, {"detail": "upstream connection error"})]
    assert hits == [URLS[0], URLS[1]]


def test_upstream_5xx_preferred_over_synthetic_error():
    hits: list[str] = []
    behaviours = {URLS[0]: "5xx", URLS[1]: "conn"}
    pool = UpstreamPool(urls=URLS, transport=_transport(behaviours, hits), retry_enabled=True)
    assert _run(pool) == [(503, {"detail": f"overloaded {URLS[0]}"})]


def test_retry_keeps_round_robin_start_rotation():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({}, hits), retry_enabled=True)
    _run(pool, n=4)
    assert hits == [URLS[0], URLS[1], URLS[2], URLS[0]]


def test_single_backend_does_not_retry():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS[:1], transport=_transport({URLS[0]: "5xx"}, hits),
                        retry_enabled=True)
    assert _run(pool)[0][0] == 503
    assert hits == [URLS[0]]


@pytest.mark.filterwarnings("error")
def test_hedge_returns_faster_backend_and_cancels_loser():
    hits: list[str] = []
    cancelled: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "hang"}, hits, cancelled),
                        hedge_enabled=True, hedge_delay_ms=20, timeout_ms=10_000)

    async def go():
        start = time.monotonic()
        result = await pool.forward({"prompt": "p"})
        elapsed = time.monotonic() - start
        leftover = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        await pool.aclose()
        return result, elapsed, leftover

    result, elapsed, leftover = asyncio.run(go())
    assert result == (200, {"completion": f"from {URLS[1]}"})
    assert elapsed < 1
    assert hits == [URLS[0], URLS[1]]
    assert cancelled == [URLS[0]]
    assert leftover == []


def test_hedge_not_fired_when_primary_is_fast():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({}, hits), hedge_enabled=True,
                        hedge_delay_ms=200)
    assert _run(pool) == [(200, {"completion": f"from {URLS[0]}"})]
    assert hits == [URLS[0]]


def test_hedge_waits_for_primary_when_hedge_fails():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "slow", URLS[1]: "5xx"}, hits),
                        hedge_enabled=True, hedge_delay_ms=20)
    assert _run(pool) == [(200, {"completion": f"from {URLS[0]}"})]
    assert hits == [URLS[0], URLS[1]]


def test_hedge_respects_max_attempts():
    hits: list[str] = []
    behaviours = {u: "slow" for u in URLS}
    pool = UpstreamPool(urls=URLS, transport=_transport(behaviours, hits), hedge_enabled=True,
                        hedge_delay_ms=10)
    assert _run(pool)[0][0] == 200
    assert hits == [URLS[0], URLS[1]]


def test_hedge_only_does_not_retry_fast_failure():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "5xx"}, hits),
                        hedge_enabled=True, hedge_delay_ms=200)
    assert _run(pool) == [(503, {"detail": f"overloaded {URLS[0]}"})]
    assert hits == [URLS[0]]


def test_retry_and_hedge_fast_failure_retries_immediately():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_transport({URLS[0]: "5xx"}, hits),
                        retry_enabled=True, hedge_enabled=True, hedge_delay_ms=5_000)
    start = time.monotonic()
    assert _run(pool) == [(200, {"completion": f"from {URLS[1]}"})]
    assert time.monotonic() - start < 1
    assert hits == [URLS[0], URLS[1]]
