from fastapi.testclient import TestClient

from app import main
from app.cache import ResponseCache
from tests.test_api import FakePool, client_with


def test_lru_eviction_and_key_order_independence():
    c = ResponseCache(max_entries=2, ttl_s=60)
    assert c.key({"a": 1, "b": 2}) == c.key({"b": 2, "a": 1})
    c.put("k1", {"v": 1})
    c.put("k2", {"v": 2})
    assert c.get("k1") == {"v": 1}  # touches k1 -> k2 is now LRU
    c.put("k3", {"v": 3})
    assert c.get("k2") is None
    assert c.get("k1") == {"v": 1}
    assert c.get("k3") == {"v": 3}


def test_ttl_expiry(monkeypatch):
    import app.cache as cache_mod

    now = [1000.0]
    monkeypatch.setattr(cache_mod.time, "monotonic", lambda: now[0])
    c = ResponseCache(max_entries=10, ttl_s=5)
    c.put("k", {"v": 1})
    now[0] += 4
    assert c.get("k") == {"v": 1}
    now[0] += 2
    assert c.get("k") is None


def test_disabled_cache_never_stores():
    c = ResponseCache(max_entries=0)
    c.put("k", {"v": 1})
    assert c.get("k") is None


def test_generate_serves_repeat_prompt_from_cache():
    pool = FakePool()
    c = client_with(pool)
    cache = main.app.state.cache = ResponseCache(max_entries=10, ttl_s=60)
    r1 = c.post("/v1/generate", json={"prompt": "hi", "max_tokens": 8})
    r2 = c.post("/v1/generate", json={"prompt": "hi", "max_tokens": 8})
    r3 = c.post("/v1/generate", json={"prompt": "hi", "max_tokens": 9})
    stats = cache.stats()
    c.__exit__(None, None, None)
    assert r1.json() == r2.json() == r3.json() == pool.body
    assert len(pool.calls) == 2  # max_tokens is part of the key
    assert stats["hits"] == 1 and stats["misses"] == 2


def test_generate_does_not_cache_errors():
    pool = FakePool(status=503, body={"detail": "overloaded"})
    c = client_with(pool)
    main.app.state.cache = ResponseCache(max_entries=10, ttl_s=60)
    c.post("/v1/generate", json={"prompt": "hi"})
    c.post("/v1/generate", json={"prompt": "hi"})
    c.__exit__(None, None, None)
    assert len(pool.calls) == 2


def test_upstreams_endpoint_reports_pool_and_cache():
    c = TestClient(main.app)
    with c:
        body = c.get("/v1/upstreams").json()
    assert "replicas" in body and "hedge_delays_ms" in body and "cache" in body
