import httpx

from .config import upstream_timeout_s, upstream_urls


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 timeout_s: float | None = None):
        self._urls = list(urls or upstream_urls())
        self._in_flight = {url: 0 for url in self._urls}
        self._cursor = 0
        self._timeout_s = upstream_timeout_s() if timeout_s is None else timeout_s
        self._client = httpx.AsyncClient(timeout=self._timeout_s, transport=transport)

    def in_flight(self) -> dict[str, int]:
        return dict(self._in_flight)

    def _pick(self, exclude: set[str]) -> str:
        """Least in-flight URL not in `exclude`.

        Ties are broken by scanning from a rotating cursor, so equally
        loaded backends are used in round-robin order.
        """
        n = len(self._urls)
        best_index = -1
        for offset in range(n):
            index = (self._cursor + offset) % n
            url = self._urls[index]
            if url in exclude:
                continue
            if best_index < 0 or self._in_flight[url] < self._in_flight[self._urls[best_index]]:
                best_index = index
        self._cursor = (best_index + 1) % n
        return self._urls[best_index]

    async def forward(self, payload: dict) -> tuple[int, dict]:
        """Send to the least-loaded backend, failing over on transport errors only.

        Non-2xx responses are returned as-is; timeouts and connect errors
        move on to the least-loaded untried backend, at most once per URL.
        """
        failures: list[dict] = []
        tried: set[str] = set()
        status = 502
        for _ in range(len(self._urls)):
            url = self._pick(tried)
            tried.add(url)
            self._in_flight[url] += 1
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
            finally:
                self._in_flight[url] -= 1
            return resp.status_code, resp.json()
        last = failures[-1]
        return status, {"detail": {**last, "attempts": failures}}

    async def aclose(self) -> None:
        await self._client.aclose()


def _failure(error: str, url: str, exc: Exception, message: str) -> dict:
    return {"error": error, "upstream": url, "message": message,
            "exception": type(exc).__name__}
