"""HTTP endpoints for the Produto (Product) domain.

Endpoints are declared with plain `def`, not `async def`: the service/repository
layers use a synchronous SQLAlchemy session, and FastAPI only runs blocking calls
off the event loop (in a threadpool) for `def` path operations. An `async def`
endpoint calling this same blocking code would block the whole event loop instead.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.produto import ProdutoCreate, ProdutoPage, ProdutoResponse, ProdutoUpdate
from app.services import produto as produto_service
from app.services.produto import ProdutoNotFoundError

router = APIRouter(prefix="/produtos", tags=["produtos"])


@router.post("", response_model=ProdutoResponse, status_code=status.HTTP_201_CREATED)
def criar_produto(data: ProdutoCreate, db: Session = Depends(get_db)) -> ProdutoResponse:
    return produto_service.create_produto(db, data)


@router.get("", response_model=ProdutoPage)
def listar_produtos(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    nome: str | None = Query(default=None, description="Partial, case-insensitive name match"),
    preco_min: Decimal | None = Query(default=None, ge=0),
    preco_max: Decimal | None = Query(default=None, ge=0),
    estoque_abaixo_de: int | None = Query(
        default=None, ge=0, description="Only products with stock below this value"
    ),
) -> ProdutoPage:
    items, total = produto_service.list_produtos(
        db,
        page=page,
        page_size=page_size,
        nome=nome,
        preco_min=preco_min,
        preco_max=preco_max,
        estoque_abaixo_de=estoque_abaixo_de,
    )
    return ProdutoPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{produto_id}", response_model=ProdutoResponse)
def buscar_produto(produto_id: int, db: Session = Depends(get_db)) -> ProdutoResponse:
    try:
        return produto_service.get_produto(db, produto_id)
    except ProdutoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto not found")


@router.patch("/{produto_id}", response_model=ProdutoResponse)
def atualizar_produto(
    produto_id: int, data: ProdutoUpdate, db: Session = Depends(get_db)
) -> ProdutoResponse:
    try:
        return produto_service.update_produto(db, produto_id, data)
    except ProdutoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto not found")


@router.delete("/{produto_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_produto(produto_id: int, db: Session = Depends(get_db)) -> None:
    try:
        produto_service.delete_produto(db, produto_id)
    except ProdutoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto not found")
