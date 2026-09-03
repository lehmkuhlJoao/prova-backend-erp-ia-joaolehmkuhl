"""Pydantic schemas for the dashboard endpoint (Part 2, Questão 4)."""

from typing import Any

from pydantic import BaseModel


class FonteResultado(BaseModel):
    fonte: str
    status: str  # "ok" or "erro"
    dados: dict[str, Any] | None = None
    erro: str | None = None


class DashboardResponse(BaseModel):
    fontes: list[FonteResultado]
    fontes_com_sucesso: list[str]
    fontes_com_falha: list[str]
    completo: bool
