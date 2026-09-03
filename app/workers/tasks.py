"""arq background tasks for the Produto domain.

Run the worker with: arq app.workers.tasks.WorkerSettings
"""

import logging

from arq.connections import RedisSettings

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.produto import Produto

logger = logging.getLogger(__name__)

ESTOQUE_BAIXO_THRESHOLD = 10


async def verificar_estoque_baixo(ctx, produto_id: int) -> dict:
    """Check a produto's current stock and log a low-stock alert if needed.

    Enqueued by PATCH /produtos/{id} when quantidade_em_estoque is reduced (see
    app/routers/produto.py) — runs here, in the worker process, well after the
    HTTP response was already sent. Opens its own DB session since it does not
    share a request-scoped one with the API process.
    """
    db = SessionLocal()
    try:
        produto = db.get(Produto, produto_id)
        if produto is None:
            logger.warning("verificar_estoque_baixo: produto %s not found", produto_id)
            return {"produto_id": produto_id, "encontrado": False}

        estoque_baixo = produto.quantidade_em_estoque < ESTOQUE_BAIXO_THRESHOLD
        if estoque_baixo:
            logger.warning(
                "ALERTA DE ESTOQUE BAIXO: produto_id=%s nome=%r quantidade_em_estoque=%s limite=%s",
                produto.id,
                produto.nome,
                produto.quantidade_em_estoque,
                ESTOQUE_BAIXO_THRESHOLD,
            )
        else:
            logger.info(
                "verificar_estoque_baixo: produto_id=%s ok, quantidade_em_estoque=%s (limite=%s)",
                produto.id,
                produto.quantidade_em_estoque,
                ESTOQUE_BAIXO_THRESHOLD,
            )

        return {
            "produto_id": produto.id,
            "encontrado": True,
            "quantidade_em_estoque": produto.quantidade_em_estoque,
            "estoque_baixo": estoque_baixo,
        }
    finally:
        db.close()


class WorkerSettings:
    functions = [verificar_estoque_baixo]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
