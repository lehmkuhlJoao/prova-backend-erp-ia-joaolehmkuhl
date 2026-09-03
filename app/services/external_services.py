"""Mocked external services for Part 2, Questão 4's fan-out demo.

Each function simulates a different downstream ERP module (estoque, financeiro,
cliente) with its own latency via asyncio.sleep, so that dashboard_service.py can
demonstrate asyncio.gather running them concurrently rather than sequentially.

Two of the three are deliberately unreliable, on purpose, so the graceful
degradation and retry logic in dashboard_service.py have something real to handle:
- consultar_cliente_service always exceeds the caller's timeout.
- consultar_financeiro_service raises on its first call in a process and only
  succeeds from the second call onward (module-level counter) — enough to show a
  single automatic retry recovering from a transient failure, deterministically.
"""

import asyncio

_financeiro_call_count = 0


async def consultar_estoque_service() -> dict:
    """Fast and reliable — simulates a healthy estoque-service."""
    await asyncio.sleep(0.3)
    return {"produtos_em_estoque": 842, "produtos_estoque_baixo": 5}


async def consultar_financeiro_service() -> dict:
    """Fails on the first call (any process), succeeds afterwards — simulates a
    transient failure that a single retry recovers from.
    """
    global _financeiro_call_count
    _financeiro_call_count += 1
    if _financeiro_call_count == 1:
        await asyncio.sleep(0.2)
        raise RuntimeError("financeiro-service temporarily unavailable")

    await asyncio.sleep(0.6)
    return {"faturamento_mes": 125430.50, "pedidos_pendentes_pagamento": 7}


async def consultar_cliente_service() -> dict:
    """Always slower than dashboard_service.TIMEOUT_SECONDS — simulates a
    downstream service that is up but too slow to answer in time.
    """
    await asyncio.sleep(5.0)
    return {"clientes_ativos": 890, "novos_clientes_mes": 34}
