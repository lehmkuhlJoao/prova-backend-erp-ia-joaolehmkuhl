"""Unit tests for dashboard_service._call_with_timeout (Part 2, Questão 4).

Uses small dummy coroutines instead of the real external_services mocks — those
sleep for seconds on purpose, to demonstrate real latency in the actual
endpoint, which would make these tests slow. TIMEOUT_SECONDS is monkeypatched
down for the timeout test so it also runs fast.
"""

import asyncio

from app.services import dashboard_service


def test_sucesso_na_primeira_tentativa():
    async def rapido():
        return {"ok": True}

    resultado = asyncio.run(dashboard_service._call_with_timeout("fonte-ok", rapido))

    assert resultado == {"fonte": "fonte-ok", "status": "ok", "dados": {"ok": True}}


def test_timeout_gera_status_erro(monkeypatch):
    monkeypatch.setattr(dashboard_service, "TIMEOUT_SECONDS", 0.05)

    async def lento():
        await asyncio.sleep(1)
        return {"nunca": "chega aqui"}

    resultado = asyncio.run(dashboard_service._call_with_timeout("fonte-lenta", lento))

    assert resultado["fonte"] == "fonte-lenta"
    assert resultado["status"] == "erro"
    assert "timeout" in resultado["erro"]


def test_retry_recupera_falha_transitoria():
    tentativas = {"count": 0}

    async def falha_na_primeira_vez():
        tentativas["count"] += 1
        if tentativas["count"] == 1:
            raise RuntimeError("falha temporaria")
        return {"recuperado": True}

    resultado = asyncio.run(
        dashboard_service._call_with_timeout("fonte-flaky", falha_na_primeira_vez, retries=1)
    )

    assert resultado == {"fonte": "fonte-flaky", "status": "ok", "dados": {"recuperado": True}}
    assert tentativas["count"] == 2


def test_falha_apos_esgotar_todas_as_tentativas():
    async def sempre_falha():
        raise RuntimeError("sempre falha")

    resultado = asyncio.run(
        dashboard_service._call_with_timeout("fonte-quebrada", sempre_falha, retries=1)
    )

    assert resultado["fonte"] == "fonte-quebrada"
    assert resultado["status"] == "erro"
    assert resultado["erro"] == "sempre falha"
