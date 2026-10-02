import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"
_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_CACHE_MAX_ENTRIES = 1024


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_number(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def cache_enabled() -> bool:
    return _env_flag("ROUTER_CACHE_ENABLED")


def cache_max_entries() -> int:
    raw = os.environ.get("ROUTER_CACHE_MAX_ENTRIES", "").strip()
    if not raw:
        return _DEFAULT_CACHE_MAX_ENTRIES
    try:
        return max(int(raw), 0)
    except ValueError:
        return _DEFAULT_CACHE_MAX_ENTRIES


def router_retry_enabled() -> bool:
    return _env_flag("ROUTER_RETRY_ENABLED")


def router_hedge_enabled() -> bool:
    return _env_flag("ROUTER_HEDGE_ENABLED")


def router_timeout_ms() -> float:
    """Per-attempt upstream timeout; only applied when retry or hedging is enabled."""
    return _env_number("ROUTER_TIMEOUT_MS", 1000)


def router_hedge_delay_ms() -> float:
    return _env_number("ROUTER_HEDGE_DELAY_MS", 250)


def router_max_attempts() -> int:
    """Upper bound on upstream attempts per request (primary + retries/hedges)."""
    return int(_env_number("ROUTER_MAX_ATTEMPTS", 2))
