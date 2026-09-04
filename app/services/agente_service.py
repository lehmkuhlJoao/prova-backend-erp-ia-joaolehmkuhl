"""Rule-based "agent" for Part 5, Questão 8.

Interprets a natural-language question in Portuguese about Produtos via regex/
keyword matching (no external LLM, no local ML model) and translates it into a
call against the existing produto_service — the same functions already used by
the CRUD endpoints, so the query logic itself is never duplicated here.

This is deliberately simple pattern matching, not real NLP — see README's
"Agente baseado em regras" section for what it can and cannot understand, and
how this would be redesigned for a real LLM (Questão 9).
"""

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services import produto as produto_service

INTENCAO_ESTOQUE_BAIXO = "estoque_baixo"
INTENCAO_PRECO_PRODUTO = "preco_produto"
INTENCAO_TOTAL_PRODUTOS = "total_produtos"

_RE_ESTOQUE_BAIXO = re.compile(
    r"estoque\s+abaixo\s+de\s+(\d+)|menos\s+de\s+(\d+)\s+unidades?",
    re.IGNORECASE,
)
_RE_PRECO_PRODUTO = re.compile(
    r"pre[çc]o\s+(?:do|da|de)\s+produto\s+(.+?)[\?\.!]*$"
    r"|quanto\s+custa\s+(?:o|a)\s+(.+?)[\?\.!]*$",
    re.IGNORECASE,
)
_RE_TOTAL_PRODUTOS = re.compile(
    r"quantos\s+produtos\s+(?:existem|h[áa]|temos|tem)",
    re.IGNORECASE,
)


def interpretar_pergunta(pergunta: str) -> tuple[str | None, dict[str, Any]]:
    """Match `pergunta` against the known patterns.

    Returns (intencao, parametros) — intencao is None when nothing matched.
    """
    match = _RE_ESTOQUE_BAIXO.search(pergunta)
    if match:
        limite = int(match.group(1) or match.group(2))
        return INTENCAO_ESTOQUE_BAIXO, {"estoque_abaixo_de": limite}

    match = _RE_PRECO_PRODUTO.search(pergunta)
    if match:
        nome = (match.group(1) or match.group(2)).strip()
        return INTENCAO_PRECO_PRODUTO, {"nome": nome}

    match = _RE_TOTAL_PRODUTOS.search(pergunta)
    if match:
        return INTENCAO_TOTAL_PRODUTOS, {}

    return None, {}


def _executar_estoque_baixo(db: Session, params: dict[str, Any]) -> dict[str, Any]:
    pagina = produto_service.list_produtos(
        db, page=1, page_size=100, estoque_abaixo_de=params["estoque_abaixo_de"]
    )
    return {
        "produtos": [p.model_dump(mode="json") for p in pagina.items],
        "total": pagina.total,
    }


def _executar_preco_produto(db: Session, params: dict[str, Any]) -> dict[str, Any]:
    pagina = produto_service.list_produtos(db, page=1, page_size=10, nome=params["nome"])
    if not pagina.items:
        return {
            "produtos": [],
            "mensagem": f"Nenhum produto encontrado com nome contendo '{params['nome']}'",
        }
    return {"produtos": [p.model_dump(mode="json") for p in pagina.items]}


def _executar_total_produtos(db: Session, params: dict[str, Any]) -> dict[str, Any]:
    # page_size=1 is enough — list_produtos already computes the total count via
    # the repository's COUNT query regardless of how many items are returned.
    pagina = produto_service.list_produtos(db, page=1, page_size=1)
    return {"total": pagina.total}


_EXECUTORES = {
    INTENCAO_ESTOQUE_BAIXO: _executar_estoque_baixo,
    INTENCAO_PRECO_PRODUTO: _executar_preco_produto,
    INTENCAO_TOTAL_PRODUTOS: _executar_total_produtos,
}


def responder_pergunta(db: Session, pergunta: str) -> dict[str, Any]:
    intencao, parametros = interpretar_pergunta(pergunta)

    if intencao is None:
        return {
            "pergunta": pergunta,
            "intencao": None,
            "parametros": {},
            "sucesso": False,
            "resultado": None,
            "erro": (
                "Não entendi a pergunta. Tente algo como 'quais produtos estão "
                "com estoque abaixo de 10 unidades?', 'qual o preço do produto "
                "Caneta Azul?' ou 'quantos produtos existem no total?'."
            ),
        }

    resultado = _EXECUTORES[intencao](db, parametros)
    return {
        "pergunta": pergunta,
        "intencao": intencao,
        "parametros": parametros,
        "sucesso": True,
        "resultado": resultado,
        "erro": None,
    }
