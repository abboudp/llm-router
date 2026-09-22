import asyncio
import random
import time
from dataclasses import dataclass, field

import httpx

from .config import (
    upstream_ewma_alpha,
    upstream_hedge_delay_s,
    upstream_timeout_s,
    upstream_urls,
)

_MAX_ATTEMPTS = 2


@dataclass
class Replica:
    url: str
    inflight: int = 0
    ewma_ms: float = 0.0
    _alpha: float = field(default=0.2, repr=False)

    def score(self) -> float:
        # Latency-weighted outstanding load; unknown replicas score 0 so they get probed.
        return self.ewma_ms * (self.inflight + 1)

    def observe(self, elapsed_ms: float) -> None:
        if self.ewma_ms == 0.0:
            self.ewma_ms = elapsed_ms
        else:
            self.ewma_ms += self._alpha * (elapsed_ms - self.ewma_ms)


class UpstreamPool:
    """Latency-aware pool: power-of-two-choices over EWMA latency x in-flight,
    a per-attempt timeout, and one hedged/retried attempt on a different replica.
    """

    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 *, timeout_s: float | None = None,
                 hedge_delay_s: float | None = None,
                 ewma_alpha: float | None = None,
                 rng: random.Random | None = None):
        alpha = upstream_ewma_alpha() if ewma_alpha is None else ewma_alpha
        self.replicas = [Replica(u, _alpha=alpha) for u in (urls or upstream_urls())]
        self._timeout_s = upstream_timeout_s() if timeout_s is None else timeout_s
        self._hedge_delay_s = upstream_hedge_delay_s() if hedge_delay_s is None else hedge_delay_s
        self._rng = rng or random.Random()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_s),
                                         transport=transport)

    def pick(self, exclude: set[str] = frozenset(), *, by_latency: bool = False) -> Replica:
        candidates = [r for r in self.replicas if r.url not in exclude] or self.replicas
        if by_latency:
            return min(candidates, key=lambda r: (r.ewma_ms, r.inflight))
        pair = candidates if len(candidates) <= 2 else self._rng.sample(candidates, 2)
        return min(pair, key=lambda r: (r.score(), r.inflight))

    async def _attempt(self, replica: Replica, payload: dict) -> tuple[int, dict]:
        replica.inflight += 1
        start = time.monotonic()
        try:
            resp = await asyncio.wait_for(
                self._client.post(f"{replica.url}/v1/completions", json=payload),
                timeout=self._timeout_s)
        except asyncio.CancelledError:
            # A cancelled hedge only tells us latency was *at least* this long.
            elapsed_ms = (time.monotonic() - start) * 1000.0
            if elapsed_ms > replica.ewma_ms:
                replica.observe(elapsed_ms)
            raise
        except Exception:
            # Timeouts and transport errors count as a full-budget miss.
            replica.observe(max((time.monotonic() - start) * 1000.0, self._timeout_s * 1000.0))
            raise
        else:
            replica.observe((time.monotonic() - start) * 1000.0)
            return resp.status_code, resp.json()
        finally:
            replica.inflight -= 1

    async def forward(self, payload: dict) -> tuple[int, dict]:
        tried: set[str] = set()
        tasks: list[asyncio.Task] = []
        errors: list[BaseException] = []

        def launch() -> None:
            # Primary pick balances load; a hedge exists to dodge a stall, so it
            # goes to the replica with the best latency estimate.
            replica = self.pick(exclude=tried, by_latency=bool(tried))
            tried.add(replica.url)
            tasks.append(asyncio.create_task(self._attempt(replica, payload)))

        launch()
        hedge_wait = self._hedge_delay_s if self._hedge_delay_s > 0 else None
        while tasks:
            can_retry = len(tried) < min(_MAX_ATTEMPTS, len(self.replicas))
            done, pending = await asyncio.wait(
                tasks, timeout=hedge_wait if can_retry else None,
                return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                tasks.remove(t)
                if t.exception() is None:
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return t.result()
                errors.append(t.exception())
            if can_retry:
                launch()  # hedge (delay elapsed) or retry (attempt failed)
                hedge_wait = None

        detail = "; ".join(f"{type(e).__name__}: {e}" for e in errors) or "no upstream available"
        return 502, {"detail": f"upstream error: {detail}"}

    async def aclose(self) -> None:
        await self._client.aclose()
