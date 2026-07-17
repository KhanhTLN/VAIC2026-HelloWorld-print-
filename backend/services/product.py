from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.product import Product
from repositories.brand import BrandRepository
from repositories.category import CategoryRepository
from repositories.product import ProductRepository
from schemas.product import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ProductRepository(session)
        self.brand_repo = BrandRepository(session)
        self.category_repo = CategoryRepository(session)

    async def _ensure_brand_exists(self, brand_id: int) -> None:
        brand = await self.brand_repo.get_by_id(brand_id)
        if brand is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Brand id={brand_id} not found",
            )

    async def _ensure_category_exists(self, category_id: int) -> None:
        category = await self.category_repo.get_by_id(category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category id={category_id} not found",
            )

    async def create(self, data: ProductCreate) -> Product:
        if data.brand_id is not None:
            await self._ensure_brand_exists(data.brand_id)
        if data.category_id is not None:
            await self._ensure_category_exists(data.category_id)

        if data.sku is not None:
            existing = await self.repo.get_by_sku(data.sku)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Product sku='{data.sku}' already exists",
                )
        return await self.repo.create(data)

    async def get(self, product_id: int) -> Product:
        product = await self.repo.get_by_id(product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product id={product_id} not found",
            )
        return product

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        category_id: int | None = None,
        brand_id: int | None = None,
    ) -> list[Product]:
        return await self.repo.list(
            skip=skip,
            limit=limit,
            category_id=category_id,
            brand_id=brand_id,
        )

    async def update(self, product_id: int, data: ProductUpdate) -> Product:
        product = await self.get(product_id)

        if data.brand_id is not None:
            await self._ensure_brand_exists(data.brand_id)
        if data.category_id is not None:
            await self._ensure_category_exists(data.category_id)

        if data.sku is not None:
            existing = await self.repo.get_by_sku(data.sku)
            if existing is not None and existing.id != product_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Product sku='{data.sku}' already exists",
                )

        return await self.repo.update(product, data)

    async def delete(self, product_id: int) -> None:
        product = await self.get(product_id)
        await self.repo.delete(product)
