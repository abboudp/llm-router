from itertools import cycle

import httpx

from .config import upstream_timeout_s, upstream_urls


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout_s: float | None = None):
        url_list = list(urls or upstream_urls())
        self._max_attempts = len(url_list)
        self._urls = cycle(url_list)
        self._timeout_s = upstream_timeout_s() if timeout_s is None else timeout_s
        self._client = httpx.AsyncClient(timeout=self._timeout_s, transport=transport)

    async def forward(self, payload: dict) -> tuple[int, dict]:
        """Send to the next backend, failing over on transport errors only.

        Non-2xx responses are returned as-is; timeouts and connect errors
        advance to the next backend, at most once per configured URL.
        """
        failures: list[dict] = []
        status = 502
        for _ in range(self._max_attempts):
            url = next(self._urls)
            try:
                resp = await self._client.post(f"{url}/v1/completions", json=payload)
            except httpx.TimeoutException as exc:
                status = 504
                failures.append(_failure("upstream_timeout", url, exc,
                                         f"upstream did not respond within {self._timeout_s}s"))
                continue
            except httpx.ConnectError as exc:
                status = 502
                failures.append(_failure("upstream_unreachable", url, exc,
                                         "could not connect to upstream"))
                continue
            return resp.status_code, resp.json()
        last = failures[-1]
        return status, {"detail": {**last, "attempts": failures}}

    async def aclose(self) -> None:
        await self._client.aclose()


def _failure(error: str, url: str, exc: Exception, message: str) -> dict:
    return {"error": error, "upstream": url, "message": message,
            "exception": type(exc).__name__}
