from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.product import ProductCreate, ProductRead, ProductUpdate
from services.product import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    return await ProductService(db).create(payload)


@router.get("", response_model=list[ProductRead])
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category_id: int | None = Query(default=None),
    brand_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[ProductRead]:
    return await ProductService(db).list(
        skip=skip,
        limit=limit,
        category_id=category_id,
        brand_id=brand_id,
    )


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    return await ProductService(db).get(product_id)


@router.put("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    return await ProductService(db).update(product_id, payload)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    await ProductService(db).delete(product_id)
