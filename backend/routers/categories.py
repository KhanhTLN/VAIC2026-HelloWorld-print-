from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from services.category import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
) -> CategoryRead:
    return await CategoryService(db).create(payload)


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryRead]:
    return await CategoryService(db).list(skip=skip, limit=limit)


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
) -> CategoryRead:
    return await CategoryService(db).get(category_id)


@router.put("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> CategoryRead:
    return await CategoryService(db).update(category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    await CategoryService(db).delete(category_id)
