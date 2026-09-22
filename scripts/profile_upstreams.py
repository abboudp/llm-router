"""Probe each upstream directly and print per-replica latency distributions.

Usage: uv run python scripts/profile_upstreams.py [requests_per_upstream]
"""
import asyncio
import os
import statistics
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import upstream_urls  # noqa: E402

PROMPTS = [
    "Summarize the following incident report in two sentences.",
    "Write a haiku about garbage collection.",
    "Explain idempotency keys to a junior engineer in three sentences.",
]


async def probe(client: httpx.AsyncClient, url: str, n: int) -> list[tuple[float, int, str]]:
    out = []
    for i in range(n):
        payload = {"prompt": f"{PROMPTS[i % len(PROMPTS)]} [{i}]", "max_tokens": 64}
        t0 = time.perf_counter()
        resp = await client.post(f"{url}/v1/completions", json=payload)
        ms = (time.perf_counter() - t0) * 1000
        out.append((ms, resp.status_code, resp.json().get("signature", "")))
    return out


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    async with httpx.AsyncClient(timeout=None) as client:
        results = await asyncio.gather(*(probe(client, u, n) for u in upstream_urls()))
    for url, rows in zip(upstream_urls(), results):
        ms = [r[0] for r in rows]
        codes = {c for _, c, _ in rows}
        print(
            f"{url}: n={n} p50={pct(ms, 50):.0f}ms p95={pct(ms, 95):.0f}ms "
            f"p99={pct(ms, 99):.0f}ms max={max(ms):.0f}ms "
            f"mean={statistics.mean(ms):.0f}ms status={sorted(codes)}"
        )
    # determinism check: same prompt on different replicas -> same signature?
    async with httpx.AsyncClient(timeout=None) as client:
        sigs = []
        for u in upstream_urls():
            r = await client.post(f"{u}/v1/completions", json={"prompt": "determinism probe", "max_tokens": 64})
            sigs.append(r.json()["signature"])
    print("same signature across replicas:", len(set(sigs)) == 1)


if __name__ == "__main__":
    asyncio.run(main())
