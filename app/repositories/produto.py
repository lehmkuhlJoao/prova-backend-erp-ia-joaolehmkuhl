"""Database access layer for the Produto domain — queries only, no business rules."""

from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.produto import Produto
from app.schemas.produto import ProdutoCreate, ProdutoUpdate


def create(db: Session, data: ProdutoCreate) -> Produto:
    produto = Produto(**data.model_dump())
    db.add(produto)
    db.commit()
    db.refresh(produto)
    return produto


def get_by_id(db: Session, produto_id: int) -> Produto | None:
    return db.get(Produto, produto_id)


def _apply_filters(
    stmt: Select,
    nome: str | None,
    preco_min: Decimal | None,
    preco_max: Decimal | None,
    estoque_abaixo_de: int | None,
) -> Select:
    if nome:
        stmt = stmt.where(Produto.nome.ilike(f"%{nome}%"))
    if preco_min is not None:
        stmt = stmt.where(Produto.preco >= preco_min)
    if preco_max is not None:
        stmt = stmt.where(Produto.preco <= preco_max)
    if estoque_abaixo_de is not None:
        stmt = stmt.where(Produto.quantidade_em_estoque < estoque_abaixo_de)
    return stmt


def list_produtos(
    db: Session,
    skip: int,
    limit: int,
    nome: str | None = None,
    preco_min: Decimal | None = None,
    preco_max: Decimal | None = None,
    estoque_abaixo_de: int | None = None,
) -> tuple[list[Produto], int]:
    base_stmt = _apply_filters(select(Produto), nome, preco_min, preco_max, estoque_abaixo_de)

    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    items = (
        db.execute(base_stmt.order_by(Produto.id).offset(skip).limit(limit))
        .scalars()
        .all()
    )

    return list(items), total


def update(db: Session, produto: Produto, data: ProdutoUpdate) -> Produto:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(produto, field, value)
    db.commit()
    db.refresh(produto)
    return produto


def delete(db: Session, produto: Produto) -> None:
    db.delete(produto)
    db.commit()
