from app.config import _env_float, upstream_max_hedges


def test_env_float_invalid_value_uses_default(monkeypatch):
    monkeypatch.setenv("LLM_HEDGE_DELAY_S", "abc")
    assert _env_float("LLM_HEDGE_DELAY_S", 0.12) == 0.12


def test_env_float_unset_uses_default(monkeypatch):
    monkeypatch.delenv("LLM_HEDGE_DELAY_S", raising=False)
    assert _env_float("LLM_HEDGE_DELAY_S", 0.12) == 0.12


def test_max_hedges_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_MAX_HEDGES", "3")
    assert upstream_max_hedges() == 3
