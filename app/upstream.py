import asyncio
import os
import time
from dataclasses import dataclass

import httpx

from .config import upstream_urls


@dataclass
class _Replica:
    url: str
    ewma_ms: float | None = None
    inflight: int = 0


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 *, hedge_after: float | None = None,
                 max_hedges: int | None = None, timeout: float = 10.0):
        self._replicas = [_Replica(url) for url in (urls or upstream_urls())]
        if hedge_after is None:
            hedge_after = float(os.getenv("LLM_HEDGE_AFTER_MS", "250")) / 1000
        if max_hedges is None:
            max_hedges = int(os.getenv("LLM_MAX_HEDGES", "1"))
        self._hedge_after = hedge_after
        self._max_hedges = max_hedges
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    def _candidates(self) -> list[_Replica]:
        return sorted(
            self._replicas,
            key=lambda replica: (
                replica.ewma_ms is not None,
                replica.ewma_ms * (replica.inflight + 1)
                if replica.ewma_ms is not None else 0,
            ),
        )

    async def _attempt(
        self, replica: _Replica, payload: dict
    ) -> tuple[int, dict]:
        started = time.monotonic()
        replica.inflight += 1
        try:
            resp = await self._client.post(
                f"{replica.url}/v1/completions", json=payload
            )
            elapsed_ms = (time.monotonic() - started) * 1000
            self._update_ewma(replica, elapsed_ms)
            return resp.status_code, resp.json()
        except asyncio.CancelledError:
            self._update_ewma(
                replica, (time.monotonic() - started) * 1000
            )
            raise
        except Exception:
            elapsed_ms = (time.monotonic() - started) * 1000
            self._update_ewma(replica, max(elapsed_ms, self._timeout * 1000))
            raise
        finally:
            replica.inflight -= 1

    @staticmethod
    def _update_ewma(replica: _Replica, elapsed_ms: float) -> None:
        if replica.ewma_ms is None:
            replica.ewma_ms = elapsed_ms
        else:
            replica.ewma_ms = 0.3 * elapsed_ms + 0.7 * replica.ewma_ms

    async def forward(self, payload: dict) -> tuple[int, dict]:
        candidates = self._candidates()
        if not candidates:
            return 502, {"error": "upstream unavailable"}

        pending: set[asyncio.Task[tuple[int, dict]]] = set()
        next_candidate = 0
        hedges_started = 0
        last_failure: tuple[int, dict] | None = None

        def launch() -> None:
            nonlocal next_candidate
            replica = candidates[next_candidate]
            next_candidate += 1
            pending.add(asyncio.create_task(self._attempt(replica, payload)))

        launch()
        next_hedge_at = time.monotonic() + self._hedge_after
        try:
            while pending or (
                hedges_started < self._max_hedges
                and next_candidate < len(candidates)
            ):
                if pending:
                    timeout = max(0, next_hedge_at - time.monotonic())
                    done, pending = await asyncio.wait(
                        pending,
                        timeout=timeout,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        try:
                            status, body = task.result()
                        except Exception:
                            continue
                        if 200 <= status < 300:
                            for loser in pending:
                                loser.cancel()
                            if pending:
                                await asyncio.gather(
                                    *pending, return_exceptions=True
                                )
                            return status, body
                        last_failure = (status, body)
                if (
                    time.monotonic() >= next_hedge_at
                    and hedges_started < self._max_hedges
                    and next_candidate < len(candidates)
                ):
                    launch()
                    hedges_started += 1
                    next_hedge_at = time.monotonic() + self._hedge_after
                elif not pending and (
                    hedges_started < self._max_hedges
                    and next_candidate < len(candidates)
                ):
                    await asyncio.sleep(
                        max(0, next_hedge_at - time.monotonic())
                    )
            if last_failure is not None:
                return last_failure
            return 502, {"error": "upstream unavailable"}
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def aclose(self) -> None:
        await self._client.aclose()
