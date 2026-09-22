import asyncio
import logging
import random
import time
from dataclasses import dataclass

import httpx

from .config import (
    upstream_ewma_alpha,
    upstream_failure_penalty,
    upstream_final_timeout_s,
    upstream_inflight_weight,
    upstream_max_retries,
    upstream_probe_fraction,
    upstream_retry_slow_factor,
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

    def score(self, inflight_weight: float) -> float:
        return self.ewma_ms * (1 + self.inflight * inflight_weight)


def _json_or_error(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"error": "upstream error"}


class UpstreamPool:
    """Selects by EWMA latency with lightly weighted inflight load.

    Failures receive a latency penalty, first attempts can probe, and retries
    prefer an untried upstream unless it is much slower than the best target.
    """

    def __init__(
        self,
        urls=None,
        transport=None,
        *,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        ewma_alpha: float | None = None,
        probe_fraction: float | None = None,
        final_timeout_s: float | None = None,
        inflight_weight: float | None = None,
        failure_penalty: float | None = None,
        retry_slow_factor: float | None = None,
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
        self._final_timeout_s = (
            upstream_final_timeout_s()
            if final_timeout_s is None
            else final_timeout_s
        )
        self._inflight_weight = (
            upstream_inflight_weight()
            if inflight_weight is None
            else inflight_weight
        )
        self._failure_penalty = (
            upstream_failure_penalty()
            if failure_penalty is None
            else failure_penalty
        )
        self._retry_slow_factor = (
            upstream_retry_slow_factor()
            if retry_slow_factor is None
            else retry_slow_factor
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

    def _select(self, tried: set[str], attempt: int) -> UpstreamState | None:
        if not self._upstreams:
            return None
        score = lambda u: u.score(self._inflight_weight)
        if attempt == 0:
            cold = [u for u in self._upstreams if u.samples == 0]
            if cold:
                return cold[0]
            if (
                len(self._upstreams) > 1
                and self._rng.random() < self._probe_fraction
            ):
                return self._rng.choice(self._upstreams)
            return min(self._upstreams, key=score)
        best_any = min(self._upstreams, key=score)
        untried = [u for u in self._upstreams if u.url not in tried]
        if untried:
            best_untried = min(untried, key=score)
            if best_untried.score(self._inflight_weight) <= (
                best_any.score(self._inflight_weight) * self._retry_slow_factor
            ):
                return best_untried
        return best_any

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
            u = self._select(tried, attempt)
            if u is None:
                break
            tried.add(u.url)
            u.inflight += 1
            start = time.perf_counter()
            deadline = self._timeout_s
            if attempt == self._max_retries and attempt > 0:
                deadline = max(self._timeout_s, self._final_timeout_s)
            penalty_ms = self._timeout_s * 1000 * self._failure_penalty
            try:
                try:
                    resp = await asyncio.wait_for(
                        self._client.post(
                            f"{u.url}/v1/completions",
                            json=payload,
                            timeout=deadline,
                        ),
                        timeout=deadline,
                    )
                except (httpx.TimeoutException, asyncio.TimeoutError):
                    self._record(u, penalty_ms)
                    last = (504, {"error": "upstream timeout"})
                    log.warning(
                        "upstream %s timed out (attempt %d)",
                        u.url,
                        attempt + 1,
                    )
                    continue
                except httpx.TransportError:
                    self._record(u, penalty_ms)
                    last = (502, {"error": "upstream unavailable"})
                    log.warning(
                        "upstream %s unavailable (attempt %d)",
                        u.url,
                        attempt + 1,
                    )
                    continue
                elapsed_ms = (time.perf_counter() - start) * 1000
                if resp.status_code >= 500:
                    self._record(u, max(elapsed_ms, penalty_ms))
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
