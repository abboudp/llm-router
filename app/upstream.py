import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from .config import (
    upstream_ewma_alpha,
    upstream_max_retries,
    upstream_probe_fraction,
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

    def score(self) -> float:
        return self.ewma_ms * (self.inflight + 1)


def _json_or_error(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"error": "upstream error"}


class UpstreamPool:
    """Selects upstreams by latency, inflight load, and occasional probes."""

    def __init__(
        self,
        urls=None,
        transport=None,
        *,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        ewma_alpha: float | None = None,
        probe_fraction: float | None = None,
        rng: random.Random | None = None,
    ):
        self._timeout_s = (
            upstream_timeout_s() if timeout_s is None else timeout_s
        )
        self._max_retries = (
            upstream_max_retries() if max_retries is None else max_retries
        )
        self._ewma_alpha = (
            upstream_ewma_alpha() if ewma_alpha is None else ewma_alpha
        )
        self._probe_fraction = (
            upstream_probe_fraction()
            if probe_fraction is None
            else probe_fraction
        )
        self._upstreams: list[UpstreamState] = [
            UpstreamState(url) for url in (urls or upstream_urls())
        ]
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout_s), transport=transport
        )
        self._rng = rng or random.Random()

    def stats(self) -> list[UpstreamState]:
        return [
            UpstreamState(u.url, u.ewma_ms, u.inflight, u.samples)
            for u in self._upstreams
        ]

    def _select(self, exclude: set[str]) -> UpstreamState | None:
        candidates = [u for u in self._upstreams if u.url not in exclude]
        if not candidates:
            return None
        cold = [u for u in candidates if u.samples == 0]
        if cold:
            return cold[0]
        if len(candidates) > 1 and self._rng.random() < self._probe_fraction:
            return self._rng.choice(candidates)
        return min(candidates, key=UpstreamState.score)

    def _record(self, u: UpstreamState, elapsed_ms: float) -> None:
        u.ewma_ms = (
            elapsed_ms
            if u.samples == 0
            else (1 - self._ewma_alpha) * u.ewma_ms
            + self._ewma_alpha * elapsed_ms
        )
        u.samples += 1

    async def forward(self, payload: dict) -> tuple[int, dict]:
        tried: set[str] = set()
        last: tuple[int, dict] | None = None
        for attempt in range(self._max_retries + 1):
            u = self._select(tried)
            if u is None:
                break
            tried.add(u.url)
            u.inflight += 1
            start = time.perf_counter()
            try:
                try:
                    resp = await asyncio.wait_for(
                        self._client.post(
                            f"{u.url}/v1/completions", json=payload
                        ),
                        timeout=self._timeout_s,
                    )
                except (httpx.TimeoutException, asyncio.TimeoutError):
                    self._record(u, self._timeout_s * 1000 * 2)
                    last = (504, {"error": "upstream timeout"})
                    log.warning(
                        "upstream %s timed out (attempt %d)",
                        u.url,
                        attempt + 1,
                    )
                    continue
                except httpx.TransportError:
                    self._record(u, self._timeout_s * 1000 * 2)
                    last = (502, {"error": "upstream unavailable"})
                    log.warning(
                        "upstream %s unavailable (attempt %d)",
                        u.url,
                        attempt + 1,
                    )
                    continue
                elapsed_ms = (time.perf_counter() - start) * 1000
                if resp.status_code >= 500:
                    self._record(
                        u, max(elapsed_ms, self._timeout_s * 1000 * 2)
                    )
                    last = (resp.status_code, _json_or_error(resp))
                    log.warning(
                        "upstream %s returned %d (attempt %d)",
                        u.url,
                        resp.status_code,
                        attempt + 1,
                    )
                    continue
                self._record(u, elapsed_ms)
                return resp.status_code, resp.json()
            finally:
                u.inflight -= 1
        assert last is not None
        return last

    async def aclose(self) -> None:
        await self._client.aclose()
