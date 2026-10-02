import asyncio
from dataclasses import dataclass
from itertools import cycle

import httpx

from .config import (
    router_hedge_delay_ms,
    router_hedge_enabled,
    router_max_attempts,
    router_retry_enabled,
    router_timeout_ms,
    upstream_urls,
)


@dataclass
class _Outcome:
    status: int
    body: dict
    retryable: bool
    from_upstream: bool


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, *,
                 retry_enabled: bool | None = None,
                 hedge_enabled: bool | None = None,
                 timeout_ms: float | None = None,
                 hedge_delay_ms: float | None = None,
                 max_attempts: int | None = None):
        self._backends = list(urls or upstream_urls())
        self._rr = cycle(range(len(self._backends)))
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
        start = next(self._rr)
        if not self._failover:
            resp = await self._client.post(f"{self._backends[start]}/v1/completions", json=payload)
            return resp.status_code, resp.json()
        n = len(self._backends)
        order = [self._backends[(start + i) % n] for i in range(self._max_attempts)]
        return await self._forward_with_failover(order, payload)

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

    async def _forward_with_failover(self, order: list[str], payload: dict) -> tuple[int, dict]:
        loop = asyncio.get_running_loop()
        pending: set[asyncio.Task[_Outcome]] = set()
        failures: list[_Outcome] = []
        launched = 0
        next_hedge_at = 0.0

        def launch() -> None:
            nonlocal launched, next_hedge_at
            pending.add(asyncio.create_task(self._attempt(order[launched], payload)))
            launched += 1
            next_hedge_at = loop.time() + self._hedge_delay

        launch()
        try:
            while pending:
                hedge_wait = None
                if self._hedge and launched < len(order):
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
                    if self._retry and launched < len(order):
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
