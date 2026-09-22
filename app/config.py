import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def upstream_hedge_delay_s() -> float:
    return _env_float("LLM_HEDGE_DELAY_S", 0.12)


def upstream_max_hedges() -> int:
    return int(_env_float("LLM_MAX_HEDGES", 3))


def upstream_timeout_s() -> float:
    return _env_float("LLM_UPSTREAM_TIMEOUT_S", 10.0)


def upstream_ewma_alpha() -> float:
    return _env_float("LLM_EWMA_ALPHA", 0.2)


def upstream_inflight_weight() -> float:
    return _env_float("LLM_INFLIGHT_WEIGHT", 0.1)


def upstream_slow_factor() -> float:
    return _env_float("LLM_SLOW_FACTOR", 3.0)


def upstream_probe_fraction() -> float:
    return _env_float("LLM_PROBE_FRACTION", 0.02)
