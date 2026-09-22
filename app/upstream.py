import asyncio
import logging
import time

import httpx

from .config import hedge_delay_s, hedge_fast_set, hedge_max, upstream_urls

log = logging.getLogger("app.upstream")

_EWMA_ALPHA = 0.2


class UpstreamPool:
    """Round-robin pool with hedged requests.

    The primary copy of each request goes to the next upstream in round-robin
    order. If it has not answered within `hedge_delay`, a duplicate is fired
    (one per elapsed delay, up to `max_hedges` extra copies) and the first 2xx
    response wins; remaining in-flight copies are cancelled.

    Hedge targets are the `fast_set` upstreams with the lowest observed
    latency (EWMA, seeded by round-robin order), cycled, with the first hedge
    always going to a different upstream than the primary. Cancelled copies
    contribute their elapsed time as a lower-bound latency sample, so a
    replica that consistently loses the race sinks in the ranking.
    """

    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 hedge_delay: float | None = None,
                 max_hedges: int | None = None,
                 fast_set: int | None = None):
        self._url_list = list(urls or upstream_urls())
        self._next = 0
        self._client = httpx.AsyncClient(timeout=None, transport=transport)
        self._hedge_delay = hedge_delay_s() if hedge_delay is None else hedge_delay
        self._max_hedges = max(0, hedge_max() if max_hedges is None else max_hedges)
        n = len(self._url_list)
        fast_set = hedge_fast_set() if fast_set is None else fast_set
        self._fast_set = max(1, min(fast_set, n)) if fast_set > 0 else n
        self._ewma: dict[str, float] = {}
        self.requests_sent = 0
        self.hedges_sent = 0

    # -- target selection --------------------------------------------------

    def _observe(self, url: str, latency: float) -> None:
        prev = self._ewma.get(url)
        self._ewma[url] = latency if prev is None else prev + _EWMA_ALPHA * (latency - prev)

    def _candidates(self) -> list[str]:
        n = len(self._url_list)
        start = self._next
        self._next = (start + 1) % n
        primary = self._url_list[start]
        if self._max_hedges == 0 or n == 1:
            return [primary] + [primary] * self._max_hedges

        rr_order = [self._url_list[(start + i) % n] for i in range(n)]
        ranked = sorted(rr_order, key=lambda u: self._ewma.get(u, 0.0))
        fast = ranked[: self._fast_set]
        if all(u == primary for u in fast):
            fast = [u for u in ranked if u != primary][:1]
        elif fast[0] == primary:
            fast = fast[1:] + fast[:1]
        hedges = [fast[i % len(fast)] for i in range(self._max_hedges)]
        return [primary] + hedges

    # -- forwarding ---------------------------------------------------------

    async def _post(self, url: str, payload: dict) -> tuple[str, int, dict]:
        started = time.monotonic()
        try:
            resp = await self._client.post(f"{url}/v1/completions", json=payload)
        except asyncio.CancelledError:
            self._observe(url, time.monotonic() - started)
            raise
        self._observe(url, time.monotonic() - started)
        return url, resp.status_code, resp.json()

    async def forward(self, payload: dict) -> tuple[int, dict]:
        candidates = self._candidates()
        pending: set[asyncio.Task] = set()
        last_result: tuple[int, dict] | None = None
        last_exc: Exception | None = None
        try:
            for i, url in enumerate(candidates):
                pending.add(asyncio.create_task(self._post(url, payload)))
                self.requests_sent += 1
                if i > 0:
                    self.hedges_sent += 1
                is_last = i == len(candidates) - 1
                while pending:
                    done, pending = await asyncio.wait(
                        pending,
                        timeout=None if is_last else self._hedge_delay,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        log.debug("hedging %s -> %s", url, candidates[i + 1])
                        break
                    for task in done:
                        try:
                            _, status, body = task.result()
                        except Exception as exc:  # noqa: BLE001 - surfaced below
                            last_exc = exc
                            continue
                        if 200 <= status < 300:
                            return status, body
                        last_result = (status, body)
            if last_result is not None:
                return last_result
            assert last_exc is not None
            raise last_exc
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def aclose(self) -> None:
        log.info("upstream copies sent=%d hedges=%d ewma_ms=%s", self.requests_sent,
                 self.hedges_sent, {u: round(v * 1000) for u, v in self._ewma.items()})
        await self._client.aclose()
