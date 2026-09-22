import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from .config import (
    upstream_ewma_alpha,
    upstream_hedge_delay_s,
    upstream_inflight_weight,
    upstream_max_hedges,
    upstream_probe_fraction,
    upstream_slow_factor,
    upstream_timeout_s,
    upstream_urls,
)

log = logging.getLogger(__name__)


@dataclass
class UpstreamState:
    url: str
    ewma_ms: float = 0.0
    inflight: int = 0
    samples: int = 0
    pending: list[float] = field(default_factory=list, repr=False, compare=False)

    def latency_ms(self, now: float) -> float:
        """EWMA once measured; until then, the age of the oldest in-flight attempt.

        A cold upstream that has not answered for a while must not keep looking
        like the best choice just because it has no samples yet.
        """
        if self.samples:
            return self.ewma_ms
        return (now - min(self.pending)) * 1000 if self.pending else 0.0

    def score(self, inflight_weight: float, now: float) -> float:
        return self.latency_ms(now) * (1 + self.inflight * inflight_weight)


@dataclass
class _Attempt:
    upstream: UpstreamState
    started: float
    task: asyncio.Task


class UpstreamPool:
    """Latency-aware selection with hedged requests.

    Each request goes to the lowest-scoring upstream (EWMA latency weighted by
    in-flight count). If no response has arrived after ``hedge_delay_s`` a
    duplicate is sent to the next-best upstream, up to ``max_hedges`` times.
    The first 2xx response wins and the remaining attempts are cancelled.
    """

    def __init__(
        self,
        urls: list[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        hedge_delay_s: float | None = None,
        max_hedges: int | None = None,
        timeout_s: float | None = None,
        ewma_alpha: float | None = None,
        probe_fraction: float | None = None,
        inflight_weight: float | None = None,
        slow_factor: float | None = None,
        rng: random.Random | None = None,
    ):
        self._upstreams = [UpstreamState(u) for u in (urls or upstream_urls())]
        self._hedge_delay_s = upstream_hedge_delay_s() if hedge_delay_s is None else hedge_delay_s
        self._max_hedges = upstream_max_hedges() if max_hedges is None else max_hedges
        self._ewma_alpha = upstream_ewma_alpha() if ewma_alpha is None else ewma_alpha
        self._probe_fraction = upstream_probe_fraction() if probe_fraction is None else probe_fraction
        self._inflight_weight = upstream_inflight_weight() if inflight_weight is None else inflight_weight
        self._slow_factor = upstream_slow_factor() if slow_factor is None else slow_factor
        self._rng = rng or random.Random()
        self._timeout_s = upstream_timeout_s() if timeout_s is None else timeout_s
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_s), transport=transport)

    def stats(self) -> list[dict]:
        return [
            {"url": u.url, "ewma_ms": u.ewma_ms, "inflight": u.inflight, "samples": u.samples}
            for u in self._upstreams
        ]

    def _candidates(self) -> list[UpstreamState]:
        """Primary plus hedge targets, best first.

        Upstreams whose latency is far worse than the best one are left out, so
        hedges cycle back over the fast set rather than waiting on a known-slow
        replica (stalls are per-request, not per-replica).
        """
        now = time.perf_counter()
        ranked = sorted(self._upstreams, key=lambda u: u.score(self._inflight_weight, now))
        if len(ranked) > 1 and self._rng.random() < self._probe_fraction:
            # occasionally promote a random upstream so a recovered replica is re-measured
            i = self._rng.randrange(1, len(ranked))
            ranked[0], ranked[i] = ranked[i], ranked[0]
        best = max(ranked[0].latency_ms(now), self._hedge_delay_s * 1000)
        fast = [u for u in ranked if u.latency_ms(now) <= best * self._slow_factor]
        return [fast[i % len(fast)] for i in range(self._max_hedges + 1)]

    def _record(self, u: UpstreamState, elapsed_ms: float) -> None:
        if u.samples == 0:
            u.ewma_ms = elapsed_ms
        else:
            u.ewma_ms = (1 - self._ewma_alpha) * u.ewma_ms + self._ewma_alpha * elapsed_ms
        u.samples += 1

    def _launch(self, u: UpstreamState, payload: dict) -> _Attempt:
        u.inflight += 1
        started = time.perf_counter()
        u.pending.append(started)
        task = asyncio.ensure_future(self._client.post(f"{u.url}/v1/completions", json=payload))
        return _Attempt(u, started, task)

    def _finish(self, a: _Attempt, elapsed_ms: float) -> None:
        a.upstream.inflight -= 1
        a.upstream.pending.remove(a.started)
        self._record(a.upstream, elapsed_ms)

    async def forward(self, payload: dict) -> tuple[int, dict]:
        if not self._upstreams:
            return 503, {"error": "no upstreams configured"}
        candidates = self._candidates()
        attempts: list[_Attempt] = [self._launch(candidates[0], payload)]
        launched = 1
        last: tuple[int, dict] = (502, {"error": "upstream unavailable"})
        penalty_ms = self._timeout_s * 1000
        try:
            while attempts or launched < len(candidates):
                if not attempts:
                    done: set[asyncio.Task] = set()
                else:
                    done, _ = await asyncio.wait(
                        [a.task for a in attempts],
                        timeout=self._hedge_delay_s if launched < len(candidates) else None,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                if not done:
                    log.info("hedging to %s", candidates[launched].url)
                    attempts.append(self._launch(candidates[launched], payload))
                    launched += 1
                    continue
                for a in [a for a in attempts if a.task in done]:
                    attempts.remove(a)
                    elapsed_ms = (time.perf_counter() - a.started) * 1000
                    try:
                        resp = a.task.result()
                    except (httpx.TimeoutException, asyncio.TimeoutError):
                        self._finish(a, penalty_ms)
                        last = (504, {"error": "upstream timeout"})
                        log.warning("upstream %s timed out", a.upstream.url)
                        continue
                    except httpx.TransportError:
                        self._finish(a, penalty_ms)
                        last = (502, {"error": "upstream unavailable"})
                        log.warning("upstream %s unavailable", a.upstream.url)
                        continue
                    if resp.status_code >= 500:
                        self._finish(a, max(elapsed_ms, penalty_ms))
                        last = (resp.status_code, _json_or_error(resp))
                        log.warning("upstream %s returned %d", a.upstream.url, resp.status_code)
                        continue
                    self._finish(a, elapsed_ms)
                    return resp.status_code, _json_or_error(resp)
            return last
        finally:
            for a in attempts:
                a.task.cancel()
                a.upstream.inflight -= 1
                a.upstream.pending.remove(a.started)
                # a cancelled attempt is only a lower bound; count it when it is worse than we thought
                elapsed_ms = (time.perf_counter() - a.started) * 1000
                if elapsed_ms > a.upstream.ewma_ms:
                    self._record(a.upstream, elapsed_ms)

    async def aclose(self) -> None:
        await self._client.aclose()


def _json_or_error(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"error": "upstream error"}
