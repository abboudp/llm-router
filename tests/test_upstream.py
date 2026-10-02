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


def test_upstream_timeout_default_and_env(monkeypatch):
    from app.config import upstream_timeout_s

    monkeypatch.delenv("UPSTREAM_TIMEOUT_S", raising=False)
    assert upstream_timeout_s() == 30.0
    monkeypatch.setenv("UPSTREAM_TIMEOUT_S", "2.5")
    assert upstream_timeout_s() == 2.5


def test_pool_uses_env_timeout(monkeypatch):
    seen: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={"completion": "ok"})

    monkeypatch.setenv("UPSTREAM_TIMEOUT_S", "7")
    pool = UpstreamPool(urls=["http://u1:9000"], transport=httpx.MockTransport(handler))

    async def run():
        await pool.forward({"prompt": "p"})
        await pool.aclose()

    asyncio.run(run())
    assert seen[0]["read"] == 7.0


def _stalling_transport() -> httpx.MockTransport:
    """Never answers; honors the client's read timeout the way a real transport would."""

    async def handler(request: httpx.Request) -> httpx.Response:
        try:
            await asyncio.wait_for(asyncio.Event().wait(), request.extensions["timeout"]["read"])
        except asyncio.TimeoutError:
            raise httpx.ReadTimeout("stalled", request=request)
        raise AssertionError("unreachable")

    return httpx.MockTransport(handler)


def test_stalled_upstream_surfaces_as_504():
    pool = UpstreamPool(urls=["http://u1:9000"], transport=_stalling_transport(), timeout_s=0.05)

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    status, body = asyncio.run(run())
    assert status == 504
    assert body["detail"]["error"] == "upstream_timeout"
    assert body["detail"]["upstream"] == "http://u1:9000"
    assert body["detail"]["exception"] == "ReadTimeout"


def test_stalled_real_socket_is_bounded():
    """A real TCP backend that accepts but never responds must not hang the pool."""

    async def run():
        async def never_respond(reader, writer):
            await asyncio.sleep(3600)

        server = await asyncio.start_server(never_respond, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        pool = UpstreamPool(urls=[f"http://127.0.0.1:{port}"], timeout_s=0.2)
        loop = asyncio.get_running_loop()
        start = loop.time()
        result = await pool.forward({"prompt": "p"})
        elapsed = loop.time() - start
        await pool.aclose()
        server.close()
        return result, elapsed

    (status, body), elapsed = asyncio.run(run())
    assert status == 504
    assert body["detail"]["error"] == "upstream_timeout"
    assert elapsed < 2


def test_connect_error_surfaces_as_502():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    pool = UpstreamPool(urls=["http://u1:9000"], transport=httpx.MockTransport(handler))

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    status, body = asyncio.run(run())
    assert status == 502
    assert body["detail"]["error"] == "upstream_unreachable"
    assert body["detail"]["upstream"] == "http://u1:9000"


def test_non_2xx_upstream_response_passes_through_unchanged():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "model overloaded"})

    pool = UpstreamPool(urls=["http://u1:9000"], transport=httpx.MockTransport(handler))

    async def run():
        result = await pool.forward({"prompt": "p"})
        await pool.aclose()
        return result

    assert asyncio.run(run()) == (503, {"detail": "model overloaded"})


def _host(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}:{request.url.port}"


def _failing_transport(hits: list[str], failing: set[str],
                       exc_type: type[httpx.TransportError] = httpx.ConnectError
                       ) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        host = _host(request)
        hits.append(host)
        if host in failing:
            raise exc_type("boom", request=request)
        return httpx.Response(200, json={"completion": f"from {host}"})

    return httpx.MockTransport(handler)


def _forward_n(pool: UpstreamPool, n: int) -> list[tuple[int, dict]]:
    async def run():
        results = [await pool.forward({"prompt": "p"}) for _ in range(n)]
        await pool.aclose()
        return results

    return asyncio.run(run())


URLS = ["http://u1:9000", "http://u2:9000", "http://u3:9000"]


def test_failover_connect_error_to_next_backend():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_failing_transport(hits, {"http://u1:9000"}))

    [(status, body)] = _forward_n(pool, 1)

    assert status == 200
    assert body == {"completion": "from http://u2:9000"}
    assert hits == ["http://u1:9000", "http://u2:9000"]


def test_failover_timeout_to_next_backend():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS,
                        transport=_failing_transport(hits, {"http://u1:9000"}, httpx.ReadTimeout))

    [(status, body)] = _forward_n(pool, 1)

    assert status == 200
    assert body == {"completion": "from http://u2:9000"}


def test_failover_all_backends_fail_bounded_by_url_count():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_failing_transport(hits, set(URLS)))

    [(status, body)] = _forward_n(pool, 1)

    assert status == 502
    assert hits == URLS  # each backend tried exactly once
    assert body["detail"]["error"] == "upstream_unreachable"
    assert [a["upstream"] for a in body["detail"]["attempts"]] == URLS


def test_failover_all_fail_with_last_timeout_is_504():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS,
                        transport=_failing_transport(hits, set(URLS), httpx.ReadTimeout))

    [(status, body)] = _forward_n(pool, 1)

    assert status == 504
    assert body["detail"]["error"] == "upstream_timeout"
    assert len(body["detail"]["attempts"]) == 3


def test_failover_does_not_retry_non_2xx():
    hits: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        hits.append(_host(request))
        return httpx.Response(503, json={"detail": "model overloaded"})

    pool = UpstreamPool(urls=URLS, transport=httpx.MockTransport(handler))

    [(status, body)] = _forward_n(pool, 1)

    assert (status, body) == (503, {"detail": "model overloaded"})
    assert hits == ["http://u1:9000"]


def test_rotation_continues_after_failover():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_failing_transport(hits, {"http://u2:9000"}))

    results = _forward_n(pool, 3)

    assert all(status == 200 for status, _ in results)
    # u1 | u2 fails -> u3 | u1  (the next request starts after the backend that served)
    assert hits == ["http://u1:9000", "http://u2:9000", "http://u3:9000", "http://u1:9000"]


def test_rotation_unchanged_when_all_healthy():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_failing_transport(hits, set()))

    _forward_n(pool, 6)

    assert hits == URLS * 2


def _gated_transport(hits: list[str], gates: dict[str, asyncio.Event]) -> httpx.MockTransport:
    """Requests to a URL with a gate block until the gate is set."""

    async def handler(request: httpx.Request) -> httpx.Response:
        host = _host(request)
        hits.append(host)
        gate = gates.get(host)
        if gate is not None:
            await gate.wait()
        return httpx.Response(200, json={"completion": f"from {host}"})

    return httpx.MockTransport(handler)


def test_least_connections_routes_around_busy_backend():
    async def run():
        hits: list[str] = []
        gate = asyncio.Event()
        pool = UpstreamPool(urls=["http://a:9000", "http://b:9000"],
                            transport=_gated_transport(hits, {"http://a:9000": gate}))
        blocked = asyncio.create_task(pool.forward({"prompt": "slow"}))
        await asyncio.sleep(0)
        while pool.in_flight()["http://a:9000"] == 0:
            await asyncio.sleep(0)

        second = await pool.forward({"prompt": "p"})
        third = await pool.forward({"prompt": "p"})
        busy_counts = pool.in_flight()

        gate.set()
        first = await blocked
        await pool.aclose()
        return hits, first, second, third, busy_counts, pool.in_flight()

    hits, first, second, third, busy_counts, final_counts = asyncio.run(run())
    assert hits == ["http://a:9000", "http://b:9000", "http://b:9000"]
    assert second == third == (200, {"completion": "from http://b:9000"})
    assert first == (200, {"completion": "from http://a:9000"})
    assert busy_counts == {"http://a:9000": 1, "http://b:9000": 0}
    assert final_counts == {"http://a:9000": 0, "http://b:9000": 0}


def test_least_connections_parallel_burst_spreads_across_all_urls():
    async def run():
        hits: list[str] = []
        gate = asyncio.Event()
        pool = UpstreamPool(urls=URLS, transport=_gated_transport(hits, {u: gate for u in URLS}))
        tasks = [asyncio.create_task(pool.forward({"prompt": "p"})) for _ in range(9)]
        while sum(pool.in_flight().values()) < 9:
            await asyncio.sleep(0)
        peak = pool.in_flight()
        gate.set()
        results = await asyncio.gather(*tasks)
        await pool.aclose()
        return hits, peak, results, pool.in_flight()

    hits, peak, results, final_counts = asyncio.run(run())
    assert peak == {u: 3 for u in URLS}
    assert sorted(hits) == sorted(URLS * 3)
    assert all(status == 200 for status, _ in results)
    assert final_counts == {u: 0 for u in URLS}


def test_least_connections_counters_balanced_after_failures():
    hits: list[str] = []
    pool = UpstreamPool(urls=URLS, transport=_failing_transport(hits, {"http://u1:9000"}))

    async def run():
        results = await asyncio.gather(*(pool.forward({"prompt": "p"}) for _ in range(6)))
        counts = pool.in_flight()
        await pool.aclose()
        return results, counts

    results, counts = asyncio.run(run())
    assert all(status == 200 for status, _ in results)
    assert counts == {u: 0 for u in URLS}

    all_fail = UpstreamPool(urls=URLS, transport=_failing_transport([], set(URLS)))

    async def run_all_fail():
        result = await all_fail.forward({"prompt": "p"})
        counts = all_fail.in_flight()
        await all_fail.aclose()
        return result, counts

    (status, _), counts = asyncio.run(run_all_fail())
    assert status == 502
    assert counts == {u: 0 for u in URLS}


def test_least_connections_tie_break_is_deterministic():
    def sequence() -> list[str]:
        hits: list[str] = []
        pool = UpstreamPool(urls=URLS, transport=_recording_transport(hits))

        async def run():
            await asyncio.gather(*(pool.forward({"prompt": "p"}) for _ in range(5)))
            for _ in range(4):
                await pool.forward({"prompt": "p"})
            await pool.aclose()

        asyncio.run(run())
        return hits

    first = sequence()
    assert first == sequence()
    assert first[:3] == URLS
