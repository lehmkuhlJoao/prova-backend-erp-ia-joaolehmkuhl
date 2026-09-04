"""Rule-based agent endpoint (Part 5, Questão 8).

Public (no JWT) and read-only, like GET /produtos — this endpoint never
mutates data, it only translates a natural-language question into one of the
existing Produto read queries.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.agente import PerguntaRequest, RespostaAgente
from app.services.agente_service import responder_pergunta

router = APIRouter(prefix="/agente", tags=["agente"])


@router.post("/perguntar", response_model=RespostaAgente)
def perguntar(data: PerguntaRequest, db: Session = Depends(get_db)) -> RespostaAgente:
    return responder_pergunta(db, data.pergunta)
