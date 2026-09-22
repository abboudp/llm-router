import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def upstream_timeout_s() -> float:
    """Hard per-attempt deadline for a single upstream call."""
    return _float_env("LLM_UPSTREAM_TIMEOUT_S", 10.0)


def upstream_hedge_delay_s() -> float:
    """Delay before a hedged attempt is fired on another replica; <= 0 disables hedging."""
    return _float_env("LLM_UPSTREAM_HEDGE_DELAY_S", 0.5)


def upstream_ewma_alpha() -> float:
    """Smoothing factor for the per-replica latency EWMA used in selection."""
    return _float_env("LLM_UPSTREAM_EWMA_ALPHA", 0.2)
