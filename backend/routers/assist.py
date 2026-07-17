from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.assist import AssistRequest, AssistResponse
from services.assist import AssistService

router = APIRouter(prefix="/assist", tags=["assist"])


@router.post("", response_model=AssistResponse)
async def assist(
    payload: AssistRequest,
    db: AsyncSession = Depends(get_db),
) -> AssistResponse:
    """
    MVP AI Shopping Assistant pipeline:

    Need (JSON) → Search → Ranking → Trade-off → Response (template tiếng Việt)
    """
    return await AssistService(db).assist(payload)
