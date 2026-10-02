import asyncio
import copy
import random
import time
from collections import OrderedDict
from collections.abc import Callable, Collection, Hashable
from dataclasses import dataclass
from itertools import cycle

import httpx

from .config import (
    cache_enabled,
    cache_max_entries,
    lb_cooldown_ms,
    lb_enabled,
    lb_ewma_alpha,
    lb_failure_threshold,
    router_hedge_delay_ms,
    router_hedge_enabled,
    router_max_attempts,
    router_retry_enabled,
    router_timeout_ms,
    upstream_urls,
)


class ResponseCache:
    """LRU cache of successful upstream responses with single-flight misses.

    All mutations happen synchronously between awaits, so the structure is
    safe under a single asyncio event loop without an explicit lock.
    """

    def __init__(self, max_entries: int):
        self.max_entries = max_entries
        self._entries: OrderedDict[Hashable, dict] = OrderedDict()
        self.inflight: dict[Hashable, asyncio.Future] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: Hashable) -> dict | None:
        body = self._entries.get(key)
        if body is None:
            return None
        self._entries.move_to_end(key)
        return copy.deepcopy(body)

    def put(self, key: Hashable, body: dict) -> None:
        self._entries[key] = copy.deepcopy(body)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


def _cache_key(payload: dict) -> Hashable | None:
    key = (payload.get("prompt"), payload.get("max_tokens"))
    try:
        hash(key)
    except TypeError:
        return None
    return key


@dataclass
class _Backend:
    url: str
    ewma: float | None = None
    inflight: int = 0
    failures: int = 0
    opened_at: float | None = None
    probing: bool = False


class LatencyBalancer:
    """Latency-aware backend selection with a per-backend circuit breaker.

    Each backend keeps an EWMA of successful response latency. Selection picks
    the healthy backend with the lowest ``ewma * (inflight + 1)`` (ties broken
    at random), so a backend's share shrinks as requests pile up on it and
    traffic never stampedes onto a single "fastest" backend. Backends with no
    samples yet borrow the best known EWMA and win ties, so every backend gets
    sampled early.

    ``failure_threshold`` consecutive failures open a backend's breaker. After
    ``cooldown_s`` a single half-open probe is sent to it; success closes the
    breaker, failure re-opens it. When no backend is selectable, selection
    falls back to plain round-robin over all backends.
    """

    def __init__(self, urls: list[str], alpha: float, failure_threshold: int,
                 cooldown_s: float, clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        self.backends = [_Backend(u) for u in urls]
        self._alpha = alpha
        self._threshold = max(1, failure_threshold)
        self._cooldown = cooldown_s
        self._clock = clock
        self._rng = rng or random.Random()
        self._fallback = cycle(self.backends)

    def _is_open(self, b: _Backend) -> bool:
        return b.opened_at is not None

    def _probe_ready(self, b: _Backend, now: float) -> bool:
        return (self._is_open(b) and not b.probing
                and now - b.opened_at >= self._cooldown)

    def acquire(self, exclude: Collection[_Backend] = ()) -> tuple[_Backend, bool]:
        """Pick a backend; returns ``(backend, is_probe)`` and marks it in flight.

        Backends in ``exclude`` are skipped unless every backend is excluded.
        """
        now = self._clock()
        skip = {id(b) for b in exclude}
        candidates = [b for b in self.backends if id(b) not in skip] or self.backends
        probe = next((b for b in candidates if self._probe_ready(b, now)), None)
        if probe is not None:
            probe.probing = True
            probe.inflight += 1
            return probe, True

        closed = [b for b in candidates if not self._is_open(b)]
        if not closed:
            b = next(self._fallback)
            for _ in range(len(self.backends) - 1):
                if b in candidates:
                    break
                b = next(self._fallback)
            b.inflight += 1
            return b, False

        known = [b.ewma for b in closed if b.ewma is not None]
        seed = min(known) if known else 1.0
        scores = {
            id(b): ((b.ewma if b.ewma is not None else seed) * (b.inflight + 1),
                    b.ewma is not None)
            for b in closed
        }
        best_score = min(scores.values())
        b = self._rng.choice([b for b in closed if scores[id(b)] == best_score])
        b.inflight += 1
        return b, False

    def release(self, b: _Backend, probe: bool, elapsed_s: float | None = None) -> None:
        """Drop an in-flight request without a health verdict (e.g. cancellation).

        ``elapsed_s`` is a lower bound on the abandoned request's latency; it is
        folded into the EWMA only when it exceeds the current estimate.
        """
        b.inflight -= 1
        if probe:
            b.probing = False
        if elapsed_s is not None and b.ewma is not None:
            elapsed_ms = elapsed_s * 1000.0
            if elapsed_ms > b.ewma:
                b.ewma = self._alpha * elapsed_ms + (1 - self._alpha) * b.ewma

    def record_success(self, b: _Backend, latency_s: float, probe: bool) -> None:
        b.inflight -= 1
        if probe:
            b.probing = False
        latency_ms = latency_s * 1000.0
        b.ewma = latency_ms if b.ewma is None else (
            self._alpha * latency_ms + (1 - self._alpha) * b.ewma)
        b.failures = 0
        b.opened_at = None

    def record_failure(self, b: _Backend, probe: bool) -> None:
        b.inflight -= 1
        b.failures += 1
        if probe:
            b.probing = False
            b.opened_at = self._clock()
        elif not self._is_open(b) and b.failures >= self._threshold:
            b.opened_at = self._clock()


@dataclass
class _Outcome:
    status: int
    body: dict
    retryable: bool
    from_upstream: bool


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 cache: bool | None = None,
                 cache_size: int | None = None, *,
                 retry_enabled: bool | None = None,
                 hedge_enabled: bool | None = None,
                 timeout_ms: float | None = None,
                 hedge_delay_ms: float | None = None,
                 max_attempts: int | None = None,
                 lb: bool | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        self._backends = list(urls or upstream_urls())
        self._rr = cycle(range(len(self._backends)))
        self._clock = clock

        enabled = cache_enabled() if cache is None else cache
        size = cache_max_entries() if cache_size is None else cache_size
        self._cache = ResponseCache(size) if enabled and size > 0 else None

        self.balancer: LatencyBalancer | None = None
        if lb if lb is not None else lb_enabled():
            self.balancer = LatencyBalancer(
                self._backends,
                alpha=lb_ewma_alpha(),
                failure_threshold=lb_failure_threshold(),
                cooldown_s=lb_cooldown_ms() / 1000.0,
                clock=clock,
                rng=rng,
            )

        self._retry = router_retry_enabled() if retry_enabled is None else retry_enabled
        self._hedge = router_hedge_enabled() if hedge_enabled is None else hedge_enabled
        self._failover = self._retry or self._hedge

        if self._failover:
            attempts = router_max_attempts() if max_attempts is None else max_attempts
            timeout_s = (router_timeout_ms() if timeout_ms is None else timeout_ms) / 1000
            delay_ms = router_hedge_delay_ms() if hedge_delay_ms is None else hedge_delay_ms
            self._max_attempts = max(1, min(attempts, len(self._backends)))
            self._attempt_timeout: float | None = timeout_s
            self._hedge_delay = delay_ms / 1000
            client_timeout: httpx.Timeout | None = httpx.Timeout(timeout_s)
        else:
            self._max_attempts = 1
            self._attempt_timeout = None
            self._hedge_delay = 0.0
            client_timeout = None
        self._client = httpx.AsyncClient(timeout=client_timeout, transport=transport)

    async def forward(self, payload: dict) -> tuple[int, dict]:
        key = _cache_key(payload) if self._cache is not None else None
        if key is None:
            return await self._dispatch(payload)
        return await self._forward_cached(key, payload)

    async def _dispatch(self, payload: dict) -> tuple[int, dict]:
        if self._failover:
            return await self._forward_with_failover(payload)
        if self.balancer is not None:
            return await self._forward_balanced(payload)
        url = self._backends[next(self._rr)]
        resp = await self._client.post(f"{url}/v1/completions", json=payload)
        return resp.status_code, resp.json()

    async def _forward_balanced(self, payload: dict) -> tuple[int, dict]:
        lb = self.balancer
        assert lb is not None
        backend, probe = lb.acquire()
        start = self._clock()
        try:
            resp = await self._client.post(f"{backend.url}/v1/completions", json=payload)
        except (httpx.TimeoutException, httpx.TransportError):
            lb.record_failure(backend, probe)
            raise
        except BaseException:
            lb.release(backend, probe)
            raise
        if resp.status_code >= 500:
            lb.record_failure(backend, probe)
        else:
            lb.record_success(backend, self._clock() - start, probe)
        return resp.status_code, resp.json()

    async def _forward_cached(self, key: Hashable, payload: dict) -> tuple[int, dict]:
        cache = self._cache
        assert cache is not None
        hit = cache.get(key)
        if hit is not None:
            return 200, hit

        leader = cache.inflight.get(key)
        if leader is not None:
            shared = await asyncio.shield(leader)
            if shared is not None:
                return 200, copy.deepcopy(shared)
            # leader failed or returned an error: make an independent attempt
            status, body = await self._dispatch(payload)
            if status == 200:
                cache.put(key, body)
            return status, body

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        cache.inflight[key] = fut
        result: dict | None = None
        try:
            status, body = await self._dispatch(payload)
            if status == 200:
                cache.put(key, body)
                result = body
            return status, body
        finally:
            cache.inflight.pop(key, None)
            if not fut.done():
                fut.set_result(copy.deepcopy(result) if result is not None else None)

    async def _attempt(self, url: str, payload: dict) -> _Outcome:
        try:
            async with asyncio.timeout(self._attempt_timeout):
                resp = await self._client.post(f"{url}/v1/completions", json=payload)
        except (httpx.TimeoutException, TimeoutError):
            return _Outcome(504, {"detail": "upstream timeout"}, True, False)
        except httpx.TransportError:
            return _Outcome(502, {"detail": "upstream connection error"}, True, False)
        if resp.status_code >= 500:
            try:
                body = resp.json()
            except ValueError:
                body = {"detail": "upstream error"}
            return _Outcome(resp.status_code, body, True, True)
        return _Outcome(resp.status_code, resp.json(), False, True)

    async def _tracked_attempt(self, backend: _Backend, probe: bool,
                               payload: dict) -> _Outcome:
        lb = self.balancer
        assert lb is not None
        start = self._clock()
        try:
            outcome = await self._attempt(backend.url, payload)
        except BaseException:
            lb.release(backend, probe, self._clock() - start)
            raise
        if outcome.retryable:
            lb.record_failure(backend, probe)
        else:
            lb.record_success(backend, self._clock() - start, probe)
        return outcome

    async def _forward_with_failover(self, payload: dict) -> tuple[int, dict]:
        loop = asyncio.get_running_loop()
        pending: set[asyncio.Task[_Outcome]] = set()
        failures: list[_Outcome] = []
        tried: list[_Backend] = []
        n = len(self._backends)
        first = 0 if self.balancer is not None else next(self._rr)
        launched = 0
        next_hedge_at = 0.0

        def launch() -> None:
            nonlocal launched, next_hedge_at
            if self.balancer is not None:
                backend, probe = self.balancer.acquire(exclude=tried)
                tried.append(backend)
                coro = self._tracked_attempt(backend, probe, payload)
            else:
                coro = self._attempt(self._backends[(first + launched) % n], payload)
            pending.add(asyncio.create_task(coro))
            launched += 1
            next_hedge_at = loop.time() + self._hedge_delay

        launch()
        try:
            while pending:
                hedge_wait = None
                if self._hedge and launched < self._max_attempts:
                    hedge_wait = max(0.0, next_hedge_at - loop.time())
                done, _ = await asyncio.wait(pending, timeout=hedge_wait,
                                             return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    launch()
                    continue
                for task in done:
                    pending.discard(task)
                    outcome = task.result()
                    if not outcome.retryable:
                        return outcome.status, outcome.body
                    failures.append(outcome)
                    if self._retry and launched < self._max_attempts:
                        launch()
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        upstream_failures = [f for f in failures if f.from_upstream]
        final = upstream_failures[-1] if upstream_failures else failures[-1]
        return final.status, final.body

    async def aclose(self) -> None:
        await self._client.aclose()
