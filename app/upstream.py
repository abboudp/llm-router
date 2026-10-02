import httpx

from .config import upstream_urls


class UpstreamPool:
    def __init__(self, urls: list[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self._urls = list(urls or upstream_urls())
        self._in_flight = {url: 0 for url in self._urls}
        self._cursor = 0
        self._client = httpx.AsyncClient(timeout=None, transport=transport)

    def in_flight(self) -> dict[str, int]:
        return dict(self._in_flight)

    def _pick(self) -> str:
        """URL with the fewest in-flight requests.

        Ties are broken by scanning from a rotating cursor, so equally
        loaded backends are used in round-robin order.
        """
        n = len(self._urls)
        best = self._cursor
        for offset in range(1, n):
            index = (self._cursor + offset) % n
            if self._in_flight[self._urls[index]] < self._in_flight[self._urls[best]]:
                best = index
        self._cursor = (best + 1) % n
        return self._urls[best]

    async def forward(self, payload: dict) -> tuple[int, dict]:
        url = self._pick()
        self._in_flight[url] += 1
        try:
            resp = await self._client.post(f"{url}/v1/completions", json=payload)
        finally:
            self._in_flight[url] -= 1
        return resp.status_code, resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()
