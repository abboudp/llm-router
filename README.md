# llm-router

llm-router is a gateway that fronts the LLM backend fleet and forwards generation requests to it, giving clients a single stable endpoint to call.

## API

### `POST /v1/generate`

Request:

```json
{
  "prompt": "Write a haiku about garbage collection.",
  "max_tokens": 64
}
```

Response:

```json
{
  "completion": "Unreachable strings...\nswept from the heap in silence...\nmemory breathes free.",
  "signature": "c4306af79b06e2249ce788596e2699f876b342f429611c76f4d75619d35117fe"
}
```

## Prerequisites

- Docker
- [uv](https://docs.astral.sh/uv/)
- [k6](https://k6.io/)
- Python 3.12

## Quickstart

In three terminals:

```bash
# terminal 1: start the backend fleet
make services

# terminal 2: start the router
make dev

# terminal 3: run the bench harness
make bench
```

## Layout

- `app/main.py` — FastAPI app and the `/v1/generate` route
- `app/upstream.py` — connection pool that forwards requests to the backend fleet
- `app/config.py` — backend URL configuration
- `bench/k6.js` — k6 load test script
- `bench/workload.json` — weighted prompt set used by the load test
- `docker-compose.yml` — backend fleet service definitions
- `Makefile` — `make services` / `make dev` / `make bench`
- `tests/` — unit tests
