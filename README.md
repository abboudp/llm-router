# llm-router

LLM gateway with a built-in playground UI — routes generation requests across a fleet of model backends and serves a chat interface for internal use.

## Prerequisites

- Docker
- [uv](https://docs.astral.sh/uv/)
- Python 3.12
- Node >= 22
- [k6](https://k6.io/)

## Quickstart

In separate terminals:

```bash
make services   # start the backend fleet
make ui         # build the playground frontend
make dev        # start the router (serves the API and the UI)
```

Open http://localhost:8000.

Other targets:

```bash
make bench   # run the k6 load harness
make e2e     # run the Playwright end-to-end UI tests
```

## API

| Method | Path                                       | Description                              |
|--------|---------------------------------------------|-------------------------------------------|
| POST   | `/v1/generate`                               | Forward a single prompt to the backend fleet |
| POST   | `/v1/chat`                                   | Send a message to a conversation and get a reply |
| GET    | `/v1/info`                                   | App name, version, and available models |
| GET    | `/v1/upstreams`                              | Per-replica latency EWMA/health, hedge and cache counters |
| GET    | `/v1/conversations?q=`                       | List conversations, optionally filtered by title |
| POST   | `/v1/conversations`                          | Create a conversation |
| PATCH  | `/v1/conversations/{id}`                     | Rename and/or pin/unpin a conversation |
| DELETE | `/v1/conversations/{id}`                     | Delete a conversation |
| GET    | `/v1/conversations/{id}/messages?limit=&before=` | List messages in a conversation, with optional pagination |
| GET    | `/v1/conversations/{id}/export`              | Download the conversation as a markdown transcript |

## Routing

`/v1/generate` is served from an in-process LRU/TTL response cache when the
same `(prompt, max_tokens)` was seen recently (upstream completions are
deterministic per prompt). Misses are forwarded with hedging + latency-aware
replica selection: a primary replica is chosen round-robin among replicas
whose EWMA latency is close to the fastest; if it has not answered within the
first hedge delay an identical request is sent to the next-best replica, and
the first successful reply wins.

| Env var                | Default    | Meaning |
|------------------------|------------|---------|
| `LLM_SERVICE_URLS`     | 3 local replicas | Comma-separated upstream base URLs |
| `HEDGE_DELAYS_MS`      | `200,120`  | Wait before the 1st, 2nd, ... hedge (one hedge per entry) |
| `SLOW_REPLICA_FACTOR`  | `3.0`      | Replica is skipped as primary when EWMA > fastest * factor + 50ms |
| `CACHE_MAX_ENTRIES`    | `1024`     | Response cache size (`0` disables) |
| `CACHE_TTL_S`          | `300`      | Response cache entry lifetime |

`uv run python scripts/profile_upstreams.py` probes each replica directly and
prints per-replica latency percentiles.

## Layout

- `app/` — FastAPI gateway: generate/chat/info routes, conversation store, markdown export, request logging middleware
- `bench/` — k6 load test script and weighted workload
- `docker-compose.yml` — backend fleet service definitions
- `frontend/` — React + TypeScript playground UI (Vite, Vitest, Testing Library, Playwright)
- `Makefile` — `make services` / `make ui` / `make dev` / `make bench` / `make e2e`
- `pyproject.toml` — Python project and dependencies (uv)
- `scripts/` — helper scripts (e2e stack bootstrap)
- `tests/` — backend unit tests (pytest)
- `uv.lock` — locked Python dependencies
