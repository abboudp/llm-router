from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .schemas import GenerateRequest
from .upstream import UpstreamPool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = UpstreamPool()
    yield
    await app.state.pool.aclose()


app = FastAPI(lifespan=lifespan)


@app.post("/v1/generate")
async def generate(req: GenerateRequest):
    status, body = await app.state.pool.forward(req.model_dump())
    return JSONResponse(status_code=status, content=body)
