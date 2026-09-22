import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def cache_ttl_s() -> float:
    """Seconds a cached upstream response stays valid. <= 0 disables the cache."""
    return float(os.environ.get("RESPONSE_CACHE_TTL_S", "60"))


def cache_max_entries() -> int:
    """Upper bound on cached responses (LRU eviction). <= 0 disables the cache."""
    return int(os.environ.get("RESPONSE_CACHE_MAX_ENTRIES", "1024"))
