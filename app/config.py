import os

_DEFAULT = "http://localhost:9001,http://localhost:9002,http://localhost:9003"


def upstream_urls() -> list[str]:
    raw = os.environ.get("LLM_SERVICE_URLS", _DEFAULT)
    return [u.strip() for u in raw.split(",") if u.strip()]


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def lb_enabled() -> bool:
    return _flag("ROUTER_LB_ENABLED")


def lb_ewma_alpha() -> float:
    return float(os.environ.get("ROUTER_LB_EWMA_ALPHA", "0.3"))


def lb_failure_threshold() -> int:
    return int(os.environ.get("ROUTER_LB_FAILURE_THRESHOLD", "3"))


def lb_cooldown_ms() -> float:
    return float(os.environ.get("ROUTER_LB_COOLDOWN_MS", "5000"))
