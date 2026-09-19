from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .upstream import UpstreamPool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = UpstreamPool()
    yield
    await app.state.pool.aclose()


app = FastAPI(lifespan=lifespan)


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 64


@app.post("/v1/generate")
async def generate(req: GenerateRequest):
    status, body = await app.state.pool.forward(req.model_dump())
    return JSONResponse(status_code=status, content=body)
