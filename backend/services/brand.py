from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.brand import Brand
from repositories.brand import BrandRepository
from schemas.brand import BrandCreate, BrandUpdate


class BrandService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = BrandRepository(session)

    async def create(self, data: BrandCreate) -> Brand:
        existing = await self.repo.get_by_name(data.name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Brand '{data.name}' already exists",
            )
        return await self.repo.create(data)

    async def get(self, brand_id: int) -> Brand:
        brand = await self.repo.get_by_id(brand_id)
        if brand is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Brand id={brand_id} not found",
            )
        return brand

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[Brand]:
        return await self.repo.list(skip=skip, limit=limit)

    async def update(self, brand_id: int, data: BrandUpdate) -> Brand:
        brand = await self.get(brand_id)
        if data.name is not None:
            existing = await self.repo.get_by_name(data.name)
            if existing is not None and existing.id != brand_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Brand '{data.name}' already exists",
                )
        return await self.repo.update(brand, data)

    async def delete(self, brand_id: int) -> None:
        brand = await self.get(brand_id)
        await self.repo.delete(brand)
