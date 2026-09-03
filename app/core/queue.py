"""Access to the shared arq Redis connection pool used to enqueue jobs.

The pool itself is created once at app startup (see app/main.py's lifespan) and
stored on app.state; this module only exposes the FastAPI dependency that reads
it back out for routers.
"""

from arq.connections import ArqRedis
from fastapi import Request


def get_arq_pool(request: Request) -> ArqRedis:
    return request.app.state.arq_pool
