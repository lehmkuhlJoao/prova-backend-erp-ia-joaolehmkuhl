"""Pydantic schemas for the rule-based agent endpoint (Part 5, Questão 8)."""

from typing import Any

from pydantic import BaseModel, Field


class PerguntaRequest(BaseModel):
    pergunta: str = Field(..., min_length=1, description="Pergunta em linguagem natural, em português")


class RespostaAgente(BaseModel):
    pergunta: str
    intencao: str | None
    parametros: dict[str, Any]
    sucesso: bool
    resultado: dict[str, Any] | None
    erro: str | None
