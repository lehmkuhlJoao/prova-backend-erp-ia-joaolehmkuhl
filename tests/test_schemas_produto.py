"""Unit tests for ProdutoCreate validation (Part 3's Pydantic requirements)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.produto import ProdutoCreate


def test_dados_validos_sao_aceitos():
    produto = ProdutoCreate(nome="Caneta Azul", preco=Decimal("2.50"), quantidade_em_estoque=100)

    assert produto.nome == "Caneta Azul"
    assert produto.preco == Decimal("2.50")
    assert produto.quantidade_em_estoque == 100


def test_preco_zero_e_aceito():
    # The exam wording is literally "não pode ser negativo" — zero is not
    # negative, so it must be allowed.
    produto = ProdutoCreate(nome="Brinde", preco=Decimal("0"), quantidade_em_estoque=0)

    assert produto.preco == Decimal("0")


def test_preco_negativo_falha():
    with pytest.raises(ValidationError):
        ProdutoCreate(nome="Caneta Azul", preco=Decimal("-1"), quantidade_em_estoque=10)


@pytest.mark.parametrize("nome_invalido", ["", "   "])
def test_nome_vazio_ou_so_espaco_falha(nome_invalido):
    with pytest.raises(ValidationError):
        ProdutoCreate(nome=nome_invalido, preco=Decimal("1"), quantidade_em_estoque=1)


def test_nome_ausente_falha():
    with pytest.raises(ValidationError):
        ProdutoCreate(preco=Decimal("1"), quantidade_em_estoque=1)


def test_nome_none_falha():
    with pytest.raises(ValidationError):
        ProdutoCreate(nome=None, preco=Decimal("1"), quantidade_em_estoque=1)


@pytest.mark.parametrize("nome_numerico", ["12345", "99.90", "-5"])
def test_nome_puramente_numerico_falha(nome_numerico):
    with pytest.raises(ValidationError):
        ProdutoCreate(nome=nome_numerico, preco=Decimal("1"), quantidade_em_estoque=1)
