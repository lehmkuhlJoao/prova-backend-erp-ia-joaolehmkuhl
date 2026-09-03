"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI

from app.core.config import settings
from app.core.database import init_db
from app.routers import auth, dashboard, produto


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Shared connection pool used to enqueue arq jobs (see app/core/queue.py) —
    # created once here instead of per-request.
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq_pool.close()


app = FastAPI(title="ERP - Produtos API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(produto.router)
app.include_router(dashboard.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight liveness check used by the Docker healthcheck (no DB/Redis calls)."""
    return {"status": "ok"}
