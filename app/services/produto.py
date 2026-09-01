"""Business logic for the Produto domain.

There is no domain-specific business rule beyond plain CRUD in this exam's scope
(e.g. no stock reservation, no pricing rules), so this layer is a thin pass-through
to the repository. It exists to keep routers free of persistence details and to
centralize the "not found" handling shared by get/update/delete.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.redis import redis_client
from app.models.produto import Produto
from app.repositories import produto as produto_repository
from app.schemas.produto import ProdutoCreate, ProdutoPage, ProdutoResponse, ProdutoUpdate

# Short TTL: bounds how stale a cached listing can be without needing active
# invalidation on writes. See README's cache section for the full rationale.
LIST_CACHE_TTL_SECONDS = 30


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


def _list_cache_key(
    page: int,
    page_size: int,
    nome: str | None,
    preco_min: Decimal | None,
    preco_max: Decimal | None,
    estoque_abaixo_de: int | None,
) -> str:
    return (
        f"produtos:list:page={page}:page_size={page_size}:"
        f"nome={nome or ''}:preco_min={preco_min if preco_min is not None else ''}:"
        f"preco_max={preco_max if preco_max is not None else ''}:"
        f"estoque_abaixo_de={estoque_abaixo_de if estoque_abaixo_de is not None else ''}"
    )


def list_produtos(
    db: Session,
    page: int,
    page_size: int,
    nome: str | None = None,
    preco_min: Decimal | None = None,
    preco_max: Decimal | None = None,
    estoque_abaixo_de: int | None = None,
) -> ProdutoPage:
    cache_key = _list_cache_key(page, page_size, nome, preco_min, preco_max, estoque_abaixo_de)

    cached = redis_client.get(cache_key)
    if cached is not None:
        return ProdutoPage.model_validate_json(cached)

    skip = (page - 1) * page_size
    items, total = produto_repository.list_produtos(
        db,
        skip=skip,
        limit=page_size,
        nome=nome,
        preco_min=preco_min,
        preco_max=preco_max,
        estoque_abaixo_de=estoque_abaixo_de,
    )
    page_result = ProdutoPage(
        items=[ProdutoResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )

    redis_client.setex(cache_key, LIST_CACHE_TTL_SECONDS, page_result.model_dump_json())
    return page_result


def update_produto(db: Session, produto_id: int, data: ProdutoUpdate) -> Produto:
    produto = get_produto(db, produto_id)
    return produto_repository.update(db, produto, data)


def delete_produto(db: Session, produto_id: int) -> None:
    produto = get_produto(db, produto_id)
    produto_repository.delete(db, produto)
