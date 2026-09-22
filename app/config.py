import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def hedge_delay_ms() -> int:
    return int(os.environ.get("LLM_HEDGE_DELAY_MS", "200"))


def probe_every() -> int:
    return int(os.environ.get("LLM_PROBE_EVERY", "50"))


def cache_ttl_s() -> int:
    return int(os.environ.get("LLM_CACHE_TTL_S", "300"))


def cache_max() -> int:
    return int(os.environ.get("LLM_CACHE_MAX", "2048"))
