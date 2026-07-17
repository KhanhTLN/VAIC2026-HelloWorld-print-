from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.search import SearchRequest, SearchResponse
from services.search import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_products(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    return await SearchService(db).search(payload)
