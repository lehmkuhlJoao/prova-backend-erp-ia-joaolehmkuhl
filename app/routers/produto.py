"""HTTP endpoints for the Produto (Product) domain.

Endpoints are declared with plain `def`, not `async def`: the service/repository
layers use a synchronous SQLAlchemy session, and FastAPI only runs blocking calls
off the event loop (in a threadpool) for `def` path operations. An `async def`
endpoint calling this same blocking code would block the whole event loop instead.

Write endpoints (POST/PATCH/DELETE) require a valid JWT; GET endpoints are public
(read access to a product catalog is treated as public data here) — see README's
"Autenticação (JWT)" section for the reasoning.

PATCH also enqueues a background job (verificar_estoque_baixo, run by the arq
worker) whenever the update reduces quantidade_em_estoque — via BackgroundTasks,
so the response is sent immediately, without waiting for the worker.
"""

from decimal import Decimal

from arq.connections import ArqRedis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.queue import get_arq_pool
from app.core.security import get_current_user
from app.schemas.produto import ProdutoCreate, ProdutoPage, ProdutoResponse, ProdutoUpdate
from app.services import produto as produto_service
from app.services.produto import ProdutoNotFoundError

router = APIRouter(prefix="/produtos", tags=["produtos"])


async def _enqueue_verificar_estoque_baixo(pool: ArqRedis, produto_id: int) -> None:
    await pool.enqueue_job("verificar_estoque_baixo", produto_id)


@router.post("", response_model=ProdutoResponse, status_code=status.HTTP_201_CREATED)
def criar_produto(
    data: ProdutoCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> ProdutoResponse:
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
    return produto_service.list_produtos(
        db,
        page=page,
        page_size=page_size,
        nome=nome,
        preco_min=preco_min,
        preco_max=preco_max,
        estoque_abaixo_de=estoque_abaixo_de,
    )


@router.get("/{produto_id}", response_model=ProdutoResponse)
def buscar_produto(produto_id: int, db: Session = Depends(get_db)) -> ProdutoResponse:
    try:
        return produto_service.get_produto(db, produto_id)
    except ProdutoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto not found")


@router.patch("/{produto_id}", response_model=ProdutoResponse)
def atualizar_produto(
    produto_id: int,
    data: ProdutoUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> ProdutoResponse:
    try:
        quantidade_antes = produto_service.get_produto(db, produto_id).quantidade_em_estoque
        produto = produto_service.update_produto(db, produto_id, data)
    except ProdutoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto not found")

    estoque_reduzido = (
        data.quantidade_em_estoque is not None and data.quantidade_em_estoque < quantidade_antes
    )
    if estoque_reduzido:
        background_tasks.add_task(_enqueue_verificar_estoque_baixo, arq_pool, produto.id)

    return produto


@router.delete("/{produto_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_produto(
    produto_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> None:
    try:
        produto_service.delete_produto(db, produto_id)
    except ProdutoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto not found")
