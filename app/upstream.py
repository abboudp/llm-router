import asyncio
import json
import logging
import time
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass

import httpx

from .config import cache_max as configured_cache_max
from .config import cache_ttl_s as configured_cache_ttl_s
from .config import hedge_delay_ms as configured_hedge_delay_ms
from .config import probe_every as configured_probe_every
from .config import upstream_urls

logger = logging.getLogger("llm-router.upstream")


@dataclass
class _Replica:
    url: str
    ewma_ms: float = 0.0
    inflight: int = 0
    failures: int = 0


class UpstreamPool:
    def __init__(
        self,
        urls: list[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        hedge_delay_ms: int | None = None,
        probe_every: int | None = None,
        cache_ttl_s: int | None = None,
        cache_max: int | None = None,
    ):
        self._replicas = [_Replica(url) for url in (urls or upstream_urls())]
        self._rr_index = 0
        self._request_count = 0
        self._hedge_delay_ms = (
            configured_hedge_delay_ms() if hedge_delay_ms is None else hedge_delay_ms
        )
        self._probe_every = (
            configured_probe_every() if probe_every is None else probe_every
        )
        self._cache_ttl_s = (
            configured_cache_ttl_s() if cache_ttl_s is None else cache_ttl_s
        )
        self._cache_max = configured_cache_max() if cache_max is None else cache_max
        self._cache: OrderedDict[str, tuple[int, dict, float]] = OrderedDict()
        self._singleflight: dict[str, asyncio.Future[tuple[int, dict]]] = {}
        self._probes: set[asyncio.Task[tuple[int, dict]]] = set()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(None, connect=5.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
            transport=transport,
        )

    async def forward(self, payload: dict) -> tuple[int, dict]:
        key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        cacheable = "max_tokens" in payload

        cached = self._cache_get(key) if cacheable else None
        if cached is not None:
            return self._copy_result(cached)

        future = self._singleflight.get(key)
        if future is not None:
            return self._copy_result(await asyncio.shield(future))

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._singleflight[key] = future
        try:
            result = await self._forward_uncached(payload)
            if cacheable:
                self._cache_put(key, result)
            future.set_result(result)
            return self._copy_result(result)
        except asyncio.CancelledError as exc:
            if not future.done():
                future.set_exception(exc)
                with suppress(BaseException):
                    future.exception()
            raise
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
                future.exception()
            raise
        finally:
            if self._singleflight.get(key) is future:
                del self._singleflight[key]

    async def aclose(self) -> None:
        for task in self._probes:
            if not task.done():
                task.cancel()
        if self._probes:
            await asyncio.gather(*self._probes, return_exceptions=True)
            self._probes.clear()
        await self._client.aclose()

    async def _forward_uncached(self, payload: dict) -> tuple[int, dict]:
        if not self._replicas:
            raise RuntimeError("UpstreamPool requires at least one URL")

        self._request_count += 1
        candidates = self._candidates()
        self._start_probe(payload)
        return await self._run_candidates(candidates, payload)

    def _candidates(self) -> list[_Replica]:
        start = self._rr_index % len(self._replicas)
        self._rr_index += 1
        rotated = self._replicas[start:] + self._replicas[:start]
        rotated.sort(key=lambda replica: int(replica.ewma_ms // 50))
        return rotated

    async def _run_candidates(
        self, candidates: list[_Replica], payload: dict
    ) -> tuple[int, dict]:
        active: dict[asyncio.Task[tuple[int, dict]], _Replica] = {}
        next_candidate = 0
        outcomes: list[tuple[str, object]] = []

        def start(replica: _Replica) -> None:
            task = asyncio.create_task(self._attempt(replica, payload))
            active[task] = replica

        start(candidates[next_candidate])
        next_candidate += 1
        try:
            while active:
                timeout = None
                if next_candidate < len(candidates):
                    timeout = max(self._hedge_delay_ms, 0) / 1000
                done, _ = await asyncio.wait(
                    active, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
                )

                if not done:
                    replica = candidates[next_candidate]
                    next_candidate += 1
                    start(replica)
                    logger.debug("hedge fired for %s", replica.url)
                    continue

                winner: tuple[int, dict] | None = None
                for task in done:
                    active.pop(task)
                    try:
                        status, body = task.result()
                    except Exception as exc:
                        outcomes.append(("exception", exc))
                        continue
                    outcomes.append(("response", (status, body)))
                    if status < 500 and winner is None:
                        winner = (status, body)

                if winner is not None:
                    await self._cancel_tasks(active)
                    return winner

                if next_candidate < len(candidates):
                    start(candidates[next_candidate])
                    next_candidate += 1

            for kind, outcome in reversed(outcomes):
                if kind == "response":
                    return outcome  # type: ignore[return-value]
            for kind, outcome in reversed(outcomes):
                if kind == "exception":
                    raise outcome  # type: ignore[misc]
            raise RuntimeError("No upstream attempts were made")
        finally:
            await self._cancel_tasks(active)

    async def _attempt(self, replica: _Replica, payload: dict) -> tuple[int, dict]:
        started = time.perf_counter()
        replica.inflight += 1
        record_sample = False
        failed = False
        try:
            async with self._client.stream(
                "POST", f"{replica.url}/v1/completions", json=payload
            ) as response:
                await response.aread()
                status = response.status_code
                body = response.json()
                record_sample = True
                failed = status >= 500
                return status, body
        except asyncio.CancelledError:
            raise
        except Exception:
            record_sample = True
            failed = True
            raise
        finally:
            replica.inflight -= 1
            if record_sample:
                if failed:
                    replica.failures += 1
                elapsed_ms = (time.perf_counter() - started) * 1000
                replica.ewma_ms = (
                    elapsed_ms
                    if replica.ewma_ms == 0
                    else 0.8 * replica.ewma_ms + 0.2 * elapsed_ms
                )

    def _start_probe(self, payload: dict) -> None:
        if (
            self._probe_every <= 0
            or self._request_count % self._probe_every != 0
            or not self._replicas
        ):
            return
        slowest = max(self._replicas, key=lambda replica: replica.ewma_ms)
        if slowest.ewma_ms <= 0:
            return
        task = asyncio.create_task(self._attempt(slowest, payload))
        self._probes.add(task)
        task.add_done_callback(self._probe_done)
        logger.debug("probe fired for %s", slowest.url)

    def _probe_done(self, task: asyncio.Task[tuple[int, dict]]) -> None:
        self._probes.discard(task)
        if not task.cancelled():
            with suppress(Exception):
                task.exception()

    async def _cancel_tasks(
        self, tasks: dict[asyncio.Task[tuple[int, dict]], _Replica]
    ) -> None:
        if not tasks:
            return
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _cache_get(self, key: str) -> tuple[int, dict] | None:
        if self._cache_ttl_s <= 0:
            return None
        cached = self._cache.get(key)
        if cached is None:
            return None
        status, body, expires_at = cached
        if expires_at <= time.monotonic():
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return status, body

    def _cache_put(self, key: str, result: tuple[int, dict]) -> None:
        if self._cache_ttl_s <= 0 or self._cache_max <= 0 or result[0] != 200:
            return
        self._cache[key] = (
            result[0],
            dict(result[1]),
            time.monotonic() + self._cache_ttl_s,
        )
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    @staticmethod
    def _copy_result(result: tuple[int, dict]) -> tuple[int, dict]:
        status, body = result
        return status, dict(body)
