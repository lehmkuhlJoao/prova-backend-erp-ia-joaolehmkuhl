"""Pydantic schemas for the Produto (Product) domain."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_nome(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("nome must not be empty")
    try:
        float(stripped)
    except ValueError:
        return stripped
    raise ValueError("nome must not be a purely numeric value")


class ProdutoBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    preco: Decimal = Field(..., ge=0, description="Must not be negative")
    quantidade_em_estoque: int

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, value: str) -> str:
        return _validate_nome(value)


class ProdutoCreate(ProdutoBase):
    """Input schema for creating a Produto (no id or timestamps)."""


class ProdutoUpdate(BaseModel):
    """Input schema for partial updates — all fields optional."""

    nome: str | None = Field(default=None, min_length=1, max_length=255)
    preco: Decimal | None = Field(default=None, ge=0, description="Must not be negative")
    quantidade_em_estoque: int | None = None

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_nome(value)


class ProdutoResponse(ProdutoBase):
    """Output schema — includes id and timestamps managed by the database."""

    id: int
    data_criacao: datetime
    data_atualizacao: datetime

    model_config = ConfigDict(from_attributes=True)


class ProdutoPage(BaseModel):
    """Paginated response for the produto listing endpoint."""

    items: list[ProdutoResponse]
    total: int
    page: int
    page_size: int
