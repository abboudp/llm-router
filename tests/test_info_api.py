from fastapi.testclient import TestClient

from app import main
from app.routes.info import AVAILABLE_MODELS, APP_NAME, APP_VERSION


def client():
    return TestClient(main.app)


def test_info_returns_name_version_and_models():
    with client() as c:
        resp = c.get("/v1/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == APP_NAME
        assert body["version"] == APP_VERSION
        assert body["models"] == AVAILABLE_MODELS


def test_info_uptime_is_non_negative_and_monotonic():
    with client() as c:
        first = c.get("/v1/info").json()["uptime_s"]
        second = c.get("/v1/info").json()["uptime_s"]
        assert first >= 0
        assert second >= first
