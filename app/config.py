import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"
_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_CACHE_MAX_ENTRIES = 1024


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def cache_enabled() -> bool:
    return os.environ.get("ROUTER_CACHE_ENABLED", "").strip().lower() in _TRUTHY


def cache_max_entries() -> int:
    raw = os.environ.get("ROUTER_CACHE_MAX_ENTRIES", "").strip()
    if not raw:
        return _DEFAULT_CACHE_MAX_ENTRIES
    try:
        return max(int(raw), 0)
    except ValueError:
        return _DEFAULT_CACHE_MAX_ENTRIES
