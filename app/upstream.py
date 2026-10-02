from itertools import cycle

import httpx

from .config import upstream_timeout_s, upstream_urls


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout_s: float | None = None):
        self._urls = cycle(urls or upstream_urls())
        self._timeout_s = upstream_timeout_s() if timeout_s is None else timeout_s
        self._client = httpx.AsyncClient(timeout=self._timeout_s, transport=transport)

    async def forward(self, payload: dict) -> tuple[int, dict]:
        url = next(self._urls)
        try:
            resp = await self._client.post(f"{url}/v1/completions", json=payload)
        except httpx.TimeoutException as exc:
            return 504, _transport_error("upstream_timeout", url, exc,
                                         f"upstream did not respond within {self._timeout_s}s")
        except httpx.ConnectError as exc:
            return 502, _transport_error("upstream_unreachable", url, exc,
                                         "could not connect to upstream")
        return resp.status_code, resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()


def _transport_error(error: str, url: str, exc: Exception, message: str) -> dict:
    return {"detail": {"error": error, "upstream": url,
                       "message": message, "exception": type(exc).__name__}}
