"""Dashboard endpoint (Part 2, Questão 4).

Fans out to 3 mocked external services concurrently via asyncio.gather,
demonstrating per-call timeout, one automatic retry, and graceful degradation.
Isolated from the Produto domain — no DB, no auth, no dependency on Part 3.

Declared as `async def` (unlike the Produto routers): unlike those, this handler
has no blocking synchronous call anywhere in its path — it's asyncio.gather and
asyncio.wait_for over async mocks all the way down, which is exactly what
`async def` is for. See app/routers/produto.py's docstring for the opposite case.
"""

from fastapi import APIRouter

from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import montar_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def obter_dashboard() -> DashboardResponse:
    return await montar_dashboard()
