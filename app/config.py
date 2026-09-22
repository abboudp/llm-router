import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def hedge_delay_s() -> float:
    """Seconds to wait for an upstream before firing a duplicate copy."""
    return float(os.environ.get("LLM_HEDGE_DELAY_MS", "150")) / 1000.0


def hedge_max() -> int:
    """Maximum number of extra (hedged) copies per request."""
    return int(os.environ.get("LLM_HEDGE_MAX", "2"))


def hedge_fast_set() -> int:
    """How many of the lowest-latency upstreams hedges are spread over (0 = all)."""
    return int(os.environ.get("LLM_HEDGE_FAST_SET", "2"))
