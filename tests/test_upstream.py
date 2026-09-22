import asyncio
import contextlib
import random
import time

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


def test_passthrough_single_upstream():
    hits: list[str] = []

    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            hits.append(request.url.host)
            return httpx.Response(200, json={"completion": "ok"})

        pool = UpstreamPool(
            urls=["http://u1:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=0,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    result = asyncio.run(run())
    assert result == (200, {"completion": "ok"})
    assert hits == ["u1"]


def test_fast_response_no_hedge():
    hits: list[str] = []

    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            hits.append(request.url.host)
            return httpx.Response(200, json={"completion": request.url.host})

        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000", "http://u3:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=2,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    result = asyncio.run(run())
    assert result[0] == 200
    assert len(hits) == 1


def test_hedge_after_delay_first_response_wins():
    hits: list[str] = []

    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            hits.append(request.url.host)
            if request.url.host == "u1":
                await asyncio.sleep(1.0)
            return httpx.Response(200, json={"completion": request.url.host})

        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000", "http://u3:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=2,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        try:
            started = time.perf_counter()
            result = await pool.forward({"prompt": "p"})
            elapsed = time.perf_counter() - started
            states = list(pool._upstreams)
            return result, elapsed, states
        finally:
            await pool.aclose()

    result, elapsed, states = asyncio.run(run())
    assert result == (200, {"completion": "u2"})
    assert set(hits) == {"u1", "u2"}
    assert elapsed < 0.5
    assert all(state.inflight == 0 and state.pending == [] for state in states)


def test_prefers_lower_ewma_after_warmup():
    hits: list[str] = []

    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            hits.append(request.url.host)
            if request.url.host == "u1":
                await asyncio.sleep(0.3)
            return httpx.Response(200, json={"completion": request.url.host})

        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=1,
            probe_fraction=0.0,
            slow_factor=2.0,
            rng=random.Random(0),
        )
        try:
            first = await pool.forward({"prompt": "p"})
            hits.clear()
            later_hits: list[list[str]] = []
            for _ in range(5):
                hits.clear()
                await pool.forward({"prompt": "p"})
                later_hits.append(list(hits))
            candidates = [u.url for u in pool._candidates()]
            return first, later_hits, candidates
        finally:
            await pool.aclose()

    first, later_hits, candidates = asyncio.run(run())
    assert first == (200, {"completion": "u2"})
    assert all(per_forward == ["u2"] for per_forward in later_hits)
    assert candidates[0] == "http://u2:9000"


def test_slow_upstream_excluded_from_hedges():
    async def run():
        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000"],
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
            hedge_delay_s=0.05,
            max_hedges=2,
            probe_fraction=0.0,
            slow_factor=2.0,
        )
        try:
            pool._upstreams[0].ewma_ms, pool._upstreams[0].samples = 300.0, 1
            pool._upstreams[1].ewma_ms, pool._upstreams[1].samples = 20.0, 1
            return [u.url for u in pool._candidates()]
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == ["http://u2:9000"] * 3


def test_cold_upstream_with_stalled_pending_not_preferred():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "u1":
                await asyncio.sleep(5)
            return httpx.Response(200, json={"completion": request.url.host})

        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=0,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        task = asyncio.create_task(pool.forward({"prompt": "p"}))
        try:
            await asyncio.sleep(0.1)
            candidates = pool._candidates()
            assert candidates[0].url == "http://u2:9000"
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await pool.aclose()

    asyncio.run(run())


def test_5xx_falls_through_to_other_upstream():
    hits: list[str] = []

    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            hits.append(request.url.host)
            if request.url.host == "u1":
                return httpx.Response(500, json={"error": "x"})
            return httpx.Response(200, json={"completion": "ok"})

        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=1,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    result = asyncio.run(run())
    assert result == (200, {"completion": "ok"})
    assert hits == ["u1", "u2"]


def test_all_fail_returns_last_error():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": request.url.host})

        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=1,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (503, {"error": "u2"})


def test_transport_error_returns_502():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        pool = UpstreamPool(
            urls=["http://u1:9000"],
            transport=httpx.MockTransport(handler),
            hedge_delay_s=0.05,
            max_hedges=0,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (502, {"error": "upstream unavailable"})


def test_no_upstreams():
    async def run():
        pool = UpstreamPool(
            urls=["http://x:1"],
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            hedge_delay_s=0.05,
            max_hedges=0,
            probe_fraction=0.0,
            rng=random.Random(0),
        )
        pool._upstreams = []
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (503, {"error": "no upstreams configured"})
