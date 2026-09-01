"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import init_db
from app.routers import produto


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ERP - Produtos API", lifespan=lifespan)

app.include_router(produto.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight liveness check used by the Docker healthcheck (no DB/Redis calls)."""
    return {"status": "ok"}
