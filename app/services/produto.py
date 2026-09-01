"""Business logic for the Produto domain.

There is no domain-specific business rule beyond plain CRUD in this exam's scope
(e.g. no stock reservation, no pricing rules), so this layer is a thin pass-through
to the repository. It exists to keep routers free of persistence details and to
centralize the "not found" handling shared by get/update/delete.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.produto import Produto
from app.repositories import produto as produto_repository
from app.schemas.produto import ProdutoCreate, ProdutoUpdate


class ProdutoNotFoundError(Exception):
    """Raised when no Produto exists with the given id."""

    def __init__(self, produto_id: int) -> None:
        self.produto_id = produto_id
        super().__init__(f"Produto {produto_id} not found")


def create_produto(db: Session, data: ProdutoCreate) -> Produto:
    return produto_repository.create(db, data)


def get_produto(db: Session, produto_id: int) -> Produto:
    produto = produto_repository.get_by_id(db, produto_id)
    if produto is None:
        raise ProdutoNotFoundError(produto_id)
    return produto


def list_produtos(
    db: Session,
    page: int,
    page_size: int,
    nome: str | None = None,
    preco_min: Decimal | None = None,
    preco_max: Decimal | None = None,
    estoque_abaixo_de: int | None = None,
) -> tuple[list[Produto], int]:
    skip = (page - 1) * page_size
    return produto_repository.list_produtos(
        db,
        skip=skip,
        limit=page_size,
        nome=nome,
        preco_min=preco_min,
        preco_max=preco_max,
        estoque_abaixo_de=estoque_abaixo_de,
    )


def update_produto(db: Session, produto_id: int, data: ProdutoUpdate) -> Produto:
    produto = get_produto(db, produto_id)
    return produto_repository.update(db, produto, data)


def delete_produto(db: Session, produto_id: int) -> None:
    produto = get_produto(db, produto_id)
    produto_repository.delete(db, produto)
