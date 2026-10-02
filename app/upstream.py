import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import cycle

import httpx

from .config import (
    lb_cooldown_ms,
    lb_enabled,
    lb_ewma_alpha,
    lb_failure_threshold,
    upstream_urls,
)


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

    def acquire(self) -> tuple[_Backend, bool]:
        """Pick a backend; returns ``(backend, is_probe)`` and marks it in flight."""
        now = self._clock()
        probe = next((b for b in self.backends if self._probe_ready(b, now)), None)
        if probe is not None:
            probe.probing = True
            probe.inflight += 1
            return probe, True

        closed = [b for b in self.backends if not self._is_open(b)]
        if not closed:
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

    def release(self, b: _Backend, probe: bool) -> None:
        """Drop an in-flight request without a health verdict (e.g. cancellation)."""
        b.inflight -= 1
        if probe:
            b.probing = False

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


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, *,
                 lb: bool | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        urls = urls or upstream_urls()
        self._urls = cycle(urls)
        self._client = httpx.AsyncClient(timeout=None, transport=transport)
        self._clock = clock
        self.balancer: LatencyBalancer | None = None
        if lb if lb is not None else lb_enabled():
            self.balancer = LatencyBalancer(
                urls,
                alpha=lb_ewma_alpha(),
                failure_threshold=lb_failure_threshold(),
                cooldown_s=lb_cooldown_ms() / 1000.0,
                clock=clock,
                rng=rng,
            )

    async def forward(self, payload: dict) -> tuple[int, dict]:
        if self.balancer is None:
            url = next(self._urls)
            resp = await self._client.post(f"{url}/v1/completions", json=payload)
            return resp.status_code, resp.json()
        return await self._forward_balanced(payload)

    async def _forward_balanced(self, payload: dict) -> tuple[int, dict]:
        lb = self.balancer
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

    async def aclose(self) -> None:
        await self._client.aclose()
