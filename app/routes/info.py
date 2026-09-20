"""App metadata: name, version, available models, and process uptime."""
import time

from fastapi import APIRouter

from ..schemas import InfoResponse

router = APIRouter(tags=["info"])

APP_NAME = "llm-router"
APP_VERSION = "0.1.0"
AVAILABLE_MODELS = ["default", "mock-large"]

_started_at = time.monotonic()


@router.get("/v1/info", response_model=InfoResponse)
async def info():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "models": AVAILABLE_MODELS,
        "uptime_s": round(time.monotonic() - _started_at, 1),
    }
