import httpx
from fastapi.testclient import TestClient

from app import main


class FakePool:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body or {"completion": "ok", "signature": "ab" * 32}
        self.calls: list[dict] = []

    async def forward(self, payload):
        self.calls.append(payload)
        return self.status, self.body

    async def aclose(self):
        pass


def client_with(pool: FakePool) -> TestClient:
    c = TestClient(main.app)
    c.__enter__()
    main.app.state.pool = pool
    return c


def _new_conversation(c: TestClient) -> str:
    return c.post("/v1/conversations", json={}).json()["id"]


def test_generate_returns_chat_turn_and_forwards_flattened_prompt():
    pool = FakePool()
    c = client_with(pool)
    cid = _new_conversation(c)
    r = c.post("/v1/generate", json={"conversation_id": cid, "message": "hi", "max_tokens": 8})
    c.__exit__(None, None, None)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"message", "latency_ms", "model", "usage"}
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "ok"
    assert body["message"]["conversation_id"] == cid
    assert len(pool.calls) == 1
    assert pool.calls[0]["prompt"].endswith("User: hi\nAssistant:")
    assert pool.calls[0]["max_tokens"] == 8


def test_generate_passes_through_error_status():
    pool = FakePool(status=503, body={"detail": "model overloaded"})
    c = client_with(pool)
    cid = _new_conversation(c)
    r = c.post("/v1/generate", json={"conversation_id": cid, "message": "hi"})
    c.__exit__(None, None, None)
    assert r.status_code == 503
    assert r.json() == {"detail": "model overloaded"}


def test_generate_rejects_legacy_prompt_only_body():
    pool = FakePool()
    c = client_with(pool)
    r = c.post("/v1/generate", json={"prompt": "hi"})
    c.__exit__(None, None, None)
    assert r.status_code == 422
    assert pool.calls == []


def test_generate_validates_body():
    pool = FakePool()
    c = client_with(pool)
    r = c.post("/v1/generate", json={})
    c.__exit__(None, None, None)
    assert r.status_code == 422
