from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.brand import BrandCreate, BrandRead, BrandUpdate
from services.brand import BrandService

router = APIRouter(prefix="/brands", tags=["brands"])


@router.post("", response_model=BrandRead, status_code=status.HTTP_201_CREATED)
async def create_brand(
    payload: BrandCreate,
    db: AsyncSession = Depends(get_db),
) -> BrandRead:
    return await BrandService(db).create(payload)


@router.get("", response_model=list[BrandRead])
async def list_brands(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[BrandRead]:
    return await BrandService(db).list(skip=skip, limit=limit)


@router.get("/{brand_id}", response_model=BrandRead)
async def get_brand(
    brand_id: int,
    db: AsyncSession = Depends(get_db),
) -> BrandRead:
    return await BrandService(db).get(brand_id)


@router.put("/{brand_id}", response_model=BrandRead)
async def update_brand(
    brand_id: int,
    payload: BrandUpdate,
    db: AsyncSession = Depends(get_db),
) -> BrandRead:
    return await BrandService(db).update(brand_id, payload)


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    brand_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    await BrandService(db).delete(brand_id)
