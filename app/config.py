import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def upstream_timeout_s() -> float:
    return _env_float("LLM_UPSTREAM_TIMEOUT_S", 0.2)


def upstream_max_retries() -> int:
    return _env_int("LLM_UPSTREAM_MAX_RETRIES", 2)


def upstream_ewma_alpha() -> float:
    return _env_float("LLM_UPSTREAM_EWMA_ALPHA", 0.3)


def upstream_probe_fraction() -> float:
    return _env_float("LLM_UPSTREAM_PROBE_FRACTION", 0.02)


def upstream_final_timeout_s() -> float:
    return _env_float("LLM_UPSTREAM_FINAL_TIMEOUT_S", 5.0)
