import asyncio
import os
import time
from itertools import cycle

import httpx

from .config import upstream_urls


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_floats(name: str, default: tuple[float, ...]) -> tuple[float, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return tuple(float(x) for x in raw.split(",") if x.strip())
    except ValueError:
        return default


class ReplicaStats:
    """EWMA of observed latency per replica, used to pick fast replicas."""

    def __init__(self, alpha: float = 0.2):
        self.alpha = alpha
        self.ewma_ms: float | None = None
        self.inflight = 0

    def record(self, ms: float, censored: bool = False) -> None:
        # A censored sample (request cancelled after `ms`) only tells us the
        # true latency was >= ms, so it must never pull the estimate down.
        if censored and self.ewma_ms is not None and ms < self.ewma_ms:
            return
        if self.ewma_ms is None:
            self.ewma_ms = ms
        else:
            self.ewma_ms += self.alpha * (ms - self.ewma_ms)


class UpstreamPool:
    """Forwards requests to the fleet using hedging + latency-aware selection.

    - A primary replica is chosen round-robin among "healthy" replicas, i.e.
      those whose EWMA latency is within `slow_factor` of the fastest one.
      Consistently slow replicas are only used as a last resort.
    - If the primary has not answered within `hedge_delays_ms[0]`, an
      identical request is sent to the next-best replica; if that one is also
      silent for `hedge_delays_ms[1]`, a third goes out, and so on (one hedge
      per entry). The first successful response wins; losers are cancelled.
      Upstream responses are deterministic per prompt, so any replica's
      answer is equivalent.
    """

    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 hedge_delays_ms: tuple[float, ...] | None = None,
                 slow_factor: float | None = None):
        self._url_list = list(urls or upstream_urls())
        self._rr = cycle(self._url_list)
        self._stats = {u: ReplicaStats() for u in self._url_list}
        self._client = httpx.AsyncClient(timeout=None, transport=transport)
        # Tail stalls are independent per request, so the second hedge can
        # fire sooner than the first: a request that already stalled once is
        # racing against a hard latency budget, not a p50.
        self.hedge_delays_ms = (hedge_delays_ms if hedge_delays_ms is not None
                                else _env_floats("HEDGE_DELAYS_MS", (200.0, 120.0)))
        self.slow_factor = slow_factor if slow_factor is not None else _env_float("SLOW_REPLICA_FACTOR", 3.0)
        # observability: how many requests needed a hedge / were won by one
        self.hedged = 0
        self.hedge_wins = 0

    # -- replica selection -------------------------------------------------

    def _healthy(self) -> list[str]:
        known = [s.ewma_ms for s in self._stats.values() if s.ewma_ms is not None]
        if not known:
            return self._url_list
        fastest = min(known)
        limit = fastest * self.slow_factor + 50
        return [u for u in self._url_list
                if self._stats[u].ewma_ms is None or self._stats[u].ewma_ms <= limit]

    def _order(self) -> list[str]:
        healthy = set(self._healthy())
        primary = next(self._rr)
        for _ in range(len(self._url_list)):
            if primary in healthy:
                break
            primary = next(self._rr)
        rest = [u for u in self._url_list if u != primary]
        rest.sort(key=lambda u: (self._stats[u].inflight, self._stats[u].ewma_ms or 0))
        healthy_rest = [u for u in rest if u in healthy]
        slow_rest = [u for u in rest if u not in healthy]
        # Prefer re-trying a healthy replica over falling back to a slow one:
        # tail stalls are per-request, a slow replica is slow every time.
        retry_healthy = [u for u in self._url_list if u in healthy]
        return [primary] + healthy_rest + retry_healthy + slow_rest

    # -- forwarding --------------------------------------------------------

    async def _attempt(self, url: str, payload: dict) -> tuple[int, dict]:
        stats = self._stats[url]
        stats.inflight += 1
        t0 = time.perf_counter()
        try:
            resp = await self._client.post(f"{url}/v1/completions", json=payload)
            stats.record((time.perf_counter() - t0) * 1000)
            return resp.status_code, resp.json()
        except asyncio.CancelledError:
            stats.record((time.perf_counter() - t0) * 1000, censored=True)
            raise
        finally:
            stats.inflight -= 1

    async def forward(self, payload: dict) -> tuple[int, dict]:
        order = self._order()
        attempts = min(len(order), len(self.hedge_delays_ms) + 1)
        pending: set[asyncio.Task] = set()
        primary: asyncio.Task | None = None
        last_result: tuple[int, dict] | None = None
        last_exc: Exception | None = None
        try:
            for i in range(attempts):
                task = asyncio.create_task(self._attempt(order[i], payload))
                pending.add(task)
                if i == 0:
                    primary = task
                else:
                    self.hedged += 1
                is_last = i == attempts - 1
                deadline = time.monotonic() + (0 if is_last else self.hedge_delays_ms[i] / 1000)
                while pending:
                    timeout = None if is_last else max(0.0, deadline - time.monotonic())
                    done, pending = await asyncio.wait(
                        pending, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
                    if not done:
                        break  # hedge delay elapsed -> launch next attempt
                    for t in done:
                        try:
                            status, body = t.result()
                        except (httpx.HTTPError, ValueError) as exc:  # transport/decode error: try others
                            last_exc = exc
                            continue
                        if status < 500:
                            if t is not primary:
                                self.hedge_wins += 1
                            return status, body
                        last_result = (status, body)
                    if not pending and not is_last:
                        break  # everything so far failed; go straight to the next replica
            if last_result is not None:
                return last_result
            assert last_exc is not None
            raise last_exc
        finally:
            for t in pending:
                t.cancel()

    def stats(self) -> dict:
        healthy = set(self._healthy())
        return {
            "hedge_delays_ms": list(self.hedge_delays_ms),
            "hedged": self.hedged,
            "hedge_wins": self.hedge_wins,
            "replicas": [
                {
                    "url": u,
                    "ewma_ms": None if s.ewma_ms is None else round(s.ewma_ms, 1),
                    "inflight": s.inflight,
                    "healthy": u in healthy,
                }
                for u, s in self._stats.items()
            ],
        }

    async def aclose(self) -> None:
        await self._client.aclose()
