"""Fan-out orchestration for the ERP dashboard (Part 2, Questão 4).

Queries the 3 mocked external services concurrently via asyncio.gather, with a
per-call timeout (asyncio.wait_for) and one automatic retry on financeiro-service.
A single source failing (timeout or exception) never aborts the others or the
overall response — _call_with_timeout always returns a result dict instead of
raising, so gather itself never needs return_exceptions=True.
"""

import asyncio
import logging

from app.services.external_services import (
    consultar_cliente_service,
    consultar_estoque_service,
    consultar_financeiro_service,
)

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 2.0


async def _call_with_timeout(nome: str, chamada, *, retries: int = 0) -> dict:
    """Run `chamada()` with a per-call timeout, retrying up to `retries` times.

    Returns {"fonte", "status": "ok", "dados"} on success, or
    {"fonte", "status": "erro", "erro"} on failure — never raises.
    """
    tentativas = retries + 1
    erro: str | None = None

    for tentativa in range(1, tentativas + 1):
        try:
            dados = await asyncio.wait_for(chamada(), timeout=TIMEOUT_SECONDS)
            return {"fonte": nome, "status": "ok", "dados": dados}
        except asyncio.TimeoutError:
            erro = f"timeout after {TIMEOUT_SECONDS}s"
        except Exception as exc:  # mocked services simulate arbitrary failures
            erro = str(exc)

        if tentativa < tentativas:
            logger.warning("%s failed (attempt %d/%d): %s", nome, tentativa, tentativas, erro)

    return {"fonte": nome, "status": "erro", "erro": erro}


async def montar_dashboard() -> dict:
    resultados = await asyncio.gather(
        _call_with_timeout("estoque-service", consultar_estoque_service),
        _call_with_timeout("financeiro-service", consultar_financeiro_service, retries=1),
        _call_with_timeout("cliente-service", consultar_cliente_service),
    )

    sucesso = [r["fonte"] for r in resultados if r["status"] == "ok"]
    falha = [r["fonte"] for r in resultados if r["status"] == "erro"]

    return {
        "fontes": resultados,
        "fontes_com_sucesso": sucesso,
        "fontes_com_falha": falha,
        "completo": not falha,
    }
