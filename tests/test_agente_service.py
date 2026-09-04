"""Unit tests for the rule-based agent (Part 5, Questão 8).

produto_service.list_produtos is monkeypatched in the responder_pergunta tests,
so these exercise only the agent's own logic (intent matching + response
shaping) — never a real database. See README's "Testes" section for why
repository/DB integration tests are a deliberately separate, deferred concern.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.produto import ProdutoPage, ProdutoResponse
from app.services import agente_service


def _produto_fake(id_: int, nome: str, preco: str, quantidade: int) -> ProdutoResponse:
    agora = datetime.now(timezone.utc)
    return ProdutoResponse(
        id=id_,
        nome=nome,
        preco=Decimal(preco),
        quantidade_em_estoque=quantidade,
        data_criacao=agora,
        data_atualizacao=agora,
    )


# --- interpretar_pergunta: pure regex matching, no DB involved ---


def test_interpretar_estoque_baixo():
    intencao, params = agente_service.interpretar_pergunta(
        "Quais produtos estão com estoque abaixo de 10 unidades?"
    )

    assert intencao == agente_service.INTENCAO_ESTOQUE_BAIXO
    assert params == {"estoque_abaixo_de": 10}


def test_interpretar_preco_produto():
    intencao, params = agente_service.interpretar_pergunta("Qual o preço do produto Caneta Azul?")

    assert intencao == agente_service.INTENCAO_PRECO_PRODUTO
    assert params == {"nome": "Caneta Azul"}


def test_interpretar_total_produtos():
    intencao, params = agente_service.interpretar_pergunta("Quantos produtos existem no total?")

    assert intencao == agente_service.INTENCAO_TOTAL_PRODUTOS
    assert params == {}


def test_interpretar_pergunta_nao_reconhecida():
    intencao, params = agente_service.interpretar_pergunta("Qual é a capital da França?")

    assert intencao is None
    assert params == {}


# --- responder_pergunta: dispatch + response shaping, produto_service mocked ---


def test_responder_estoque_baixo(monkeypatch):
    pagina = ProdutoPage(items=[_produto_fake(1, "Caderno Grande", "15.90", 3)], total=1, page=1, page_size=100)
    chamada_kwargs = {}

    def fake_list_produtos(db, **kwargs):
        chamada_kwargs.update(kwargs)
        return pagina

    monkeypatch.setattr(agente_service.produto_service, "list_produtos", fake_list_produtos)

    resposta = agente_service.responder_pergunta(None, "estoque abaixo de 10 unidades")

    assert resposta["sucesso"] is True
    assert resposta["intencao"] == agente_service.INTENCAO_ESTOQUE_BAIXO
    assert resposta["parametros"] == {"estoque_abaixo_de": 10}
    assert resposta["resultado"]["total"] == 1
    assert resposta["resultado"]["produtos"][0]["nome"] == "Caderno Grande"
    assert chamada_kwargs["estoque_abaixo_de"] == 10


def test_responder_preco_produto_encontrado(monkeypatch):
    pagina = ProdutoPage(items=[_produto_fake(2, "Caneta Azul", "2.50", 100)], total=1, page=1, page_size=10)
    monkeypatch.setattr(agente_service.produto_service, "list_produtos", lambda db, **kw: pagina)

    resposta = agente_service.responder_pergunta(None, "qual o preço do produto Caneta Azul?")

    assert resposta["sucesso"] is True
    assert resposta["parametros"] == {"nome": "Caneta Azul"}
    assert resposta["resultado"]["produtos"][0]["preco"] == "2.50"


def test_responder_preco_produto_nao_encontrado(monkeypatch):
    pagina_vazia = ProdutoPage(items=[], total=0, page=1, page_size=10)
    monkeypatch.setattr(agente_service.produto_service, "list_produtos", lambda db, **kw: pagina_vazia)

    resposta = agente_service.responder_pergunta(None, "qual o preço do produto Inexistente?")

    # The question WAS understood — it just found nothing. Different from the
    # "não entendi" case below.
    assert resposta["sucesso"] is True
    assert resposta["resultado"]["produtos"] == []
    assert "mensagem" in resposta["resultado"]


def test_responder_total_produtos(monkeypatch):
    pagina = ProdutoPage(items=[], total=42, page=1, page_size=1)
    monkeypatch.setattr(agente_service.produto_service, "list_produtos", lambda db, **kw: pagina)

    resposta = agente_service.responder_pergunta(None, "quantos produtos existem no total?")

    assert resposta["sucesso"] is True
    assert resposta["resultado"] == {"total": 42}


def test_responder_pergunta_nao_reconhecida():
    resposta = agente_service.responder_pergunta(None, "qual é a capital da França?")

    assert resposta["sucesso"] is False
    assert resposta["intencao"] is None
    assert resposta["resultado"] is None
    assert resposta["erro"] is not None
    assert "não entendi" in resposta["erro"].lower()
