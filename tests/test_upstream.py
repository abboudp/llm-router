import asyncio

import httpx

from app.config import (
    upstream_ewma_alpha,
    upstream_final_timeout_s,
    upstream_max_retries,
    upstream_probe_fraction,
    upstream_timeout_s,
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


def test_upstream_settings_default(monkeypatch):
    for name in (
        "LLM_UPSTREAM_TIMEOUT_S",
        "LLM_UPSTREAM_MAX_RETRIES",
        "LLM_UPSTREAM_EWMA_ALPHA",
        "LLM_UPSTREAM_PROBE_FRACTION",
        "LLM_UPSTREAM_FINAL_TIMEOUT_S",
    ):
        monkeypatch.delenv(name, raising=False)
    assert upstream_timeout_s() == 0.2
    assert upstream_max_retries() == 2
    assert upstream_ewma_alpha() == 0.3
    assert upstream_probe_fraction() == 0.02
    assert upstream_final_timeout_s() == 5.0


def test_upstream_settings_env(monkeypatch):
    monkeypatch.setenv("LLM_UPSTREAM_TIMEOUT_S", "0.1")
    monkeypatch.setenv("LLM_UPSTREAM_MAX_RETRIES", "4")
    monkeypatch.setenv("LLM_UPSTREAM_EWMA_ALPHA", "0.7")
    monkeypatch.setenv("LLM_UPSTREAM_PROBE_FRACTION", "0.2")
    monkeypatch.setenv("LLM_UPSTREAM_FINAL_TIMEOUT_S", "1.5")
    assert upstream_timeout_s() == 0.1
    assert upstream_max_retries() == 4
    assert upstream_ewma_alpha() == 0.7
    assert upstream_probe_fraction() == 0.2
    assert upstream_final_timeout_s() == 1.5


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _url(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}:{request.url.port}"


def test_cold_start_probes_each_upstream_once_and_passthrough():
    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_url(request))
        return httpx.Response(200, json={"completion": "ok"})

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            probe_fraction=0,
        )
        try:
            return [await pool.forward({"prompt": "p"}) for _ in range(3)]
        finally:
            await pool.aclose()

    results = asyncio.run(run())
    assert hits == urls
    assert results == [(200, {"completion": "ok"})] * 3


def test_prefers_lowest_latency_upstream():
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _url(request)
        hits.append(host)
        if host == "http://u3:9000":
            await asyncio.sleep(0.05)
        return httpx.Response(200, json={"completion": "ok"})

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            timeout_s=0.2,
            probe_fraction=0,
        )
        try:
            for _ in range(3):
                await pool.forward({"prompt": "warm"})
            hits.clear()
            for _ in range(20):
                await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    asyncio.run(run())
    assert "http://u3:9000" not in hits


def test_timeout_retries_on_different_upstream():
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _url(request)
        hits.append(host)
        if host == "http://u1:9000":
            await asyncio.sleep(0.5)
        return httpx.Response(200, json={"completion": "ok"})

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            timeout_s=0.05,
            probe_fraction=0,
        )
        try:
            result = await pool.forward({"prompt": "p"})
            return result, pool.stats()
        finally:
            await pool.aclose()

    result, stats = asyncio.run(run())
    assert hits == urls
    assert result == (200, {"completion": "ok"})
    assert stats[0].ewma_ms == 100
    assert stats[0].inflight == 0


def test_final_attempt_uses_longer_timeout():
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _url(request)
        hits.append(host)
        if host in ("http://u1:9000", "http://u2:9000"):
            await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(0.1)
        return httpx.Response(200, json={"completion": "ok"})

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            timeout_s=0.05,
            final_timeout_s=1.0,
            max_retries=2,
            probe_fraction=0,
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (200, {"completion": "ok"})
    assert hits == urls


def test_5xx_retries_on_different_upstream():
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _url(request)
        hits.append(host)
        if host == "http://u1:9000":
            return httpx.Response(500, json={"error": "x"})
        return httpx.Response(200, json={"completion": "ok"})

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            probe_fraction=0,
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (200, {"completion": "ok"})
    assert hits == urls


def test_connect_error_retries():
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _url(request)
        hits.append(host)
        if host == "http://u1:9000":
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"completion": "ok"})

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            probe_fraction=0,
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (200, {"completion": "ok"})
    assert hits == urls


def test_retries_exhausted_returns_last_error():
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        hits.append(_url(request))
        await asyncio.sleep(0.5)
        return httpx.Response(200, json={"completion": "ok"})

    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]
    hits: list[str] = []

    async def run_timeout():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(timeout_handler),
            timeout_s=0.01,
            final_timeout_s=0.01,
            max_retries=2,
            probe_fraction=0,
        )
        try:
            return await pool.forward({"prompt": "p"}), pool.stats()
        finally:
            await pool.aclose()

    result, stats = asyncio.run(run_timeout())
    assert result == (504, {"error": "upstream timeout"})
    assert hits == urls
    assert all(u.inflight == 0 for u in stats)

    async def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "x"})

    async def run_error():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(error_handler),
            max_retries=2,
            probe_fraction=0,
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run_error()) == (500, {"error": "x"})


def test_max_retries_zero_no_retry():
    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_url(request))
        return httpx.Response(500, json={"error": "x"})

    hits: list[str] = []

    async def run():
        pool = UpstreamPool(
            urls=["http://u1:9000", "http://u2:9000"],
            transport=_transport(handler),
            max_retries=0,
            probe_fraction=0,
        )
        try:
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (500, {"error": "x"})
    assert hits == ["http://u1:9000"]


def test_probe_fraction_sends_traffic_to_slow_upstream():
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _url(request)
        hits.append(host)
        if host == "http://u3:9000":
            await asyncio.sleep(0.02)
        return httpx.Response(200, json={"completion": "ok"})

    class FakeRng:
        def random(self):
            return 0.0

        def choice(self, sequence):
            return sequence[-1]

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            timeout_s=0.05,
            probe_fraction=0,
            rng=FakeRng(),
        )
        try:
            for _ in range(3):
                await pool.forward({"prompt": "warm"})
            pool._probe_fraction = 1.0
            hits.clear()
            await pool.forward({"prompt": "probe"})
        finally:
            await pool.aclose()

    asyncio.run(run())
    assert hits == ["http://u3:9000"]


def test_retries_do_not_probe():
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _url(request)
        hits.append(host)
        if host == "http://u2:9000":
            await asyncio.sleep(0.02)
        elif host == "http://u3:9000":
            await asyncio.sleep(0.05)
        if host == "http://u4:9000":
            return httpx.Response(500, json={"error": "x"})
        return httpx.Response(200, json={"completion": "ok"})

    class FakeRng:
        def random(self):
            return 0.0

        def choice(self, sequence):
            return sequence[-1]

    hits: list[str] = []
    urls = [
        "http://u1:9000",
        "http://u2:9000",
        "http://u3:9000",
        "http://u4:9000",
    ]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            max_retries=1,
            probe_fraction=0,
            rng=FakeRng(),
        )
        try:
            for _ in range(4):
                await pool.forward({"prompt": "warm"})
            pool._probe_fraction = 1.0
            hits.clear()
            return await pool.forward({"prompt": "p"})
        finally:
            await pool.aclose()

    assert asyncio.run(run()) == (200, {"completion": "ok"})
    assert hits == ["http://u4:9000", "http://u1:9000"]


def test_inflight_score_spreads_concurrent_load():
    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_url(request))
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"completion": "ok"})

    hits: list[str] = []
    urls = ["http://u1:9000", "http://u2:9000"]

    async def run():
        pool = UpstreamPool(
            urls=urls,
            transport=_transport(handler),
            timeout_s=0.2,
            probe_fraction=0,
        )
        try:
            await pool.forward({"prompt": "warm"})
            await pool.forward({"prompt": "warm"})
            hits.clear()
            return await asyncio.gather(
                *(pool.forward({"prompt": "p"}) for _ in range(10))
            )
        finally:
            await pool.aclose()

    results = asyncio.run(run())
    assert all(result == (200, {"completion": "ok"}) for result in results)
    assert set(hits) == set(urls)
