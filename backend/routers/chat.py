from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.chat import ChatRequest, ChatResponse
from services.chat import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Tư vấn hội thoại:
    - Nêu tên sản phẩm → trả kết quả luôn
    - Nêu ngành hàng → hỏi 3 tiêu chí → gợi ý Top 3
    """
    return await ChatService(db).handle(payload)
