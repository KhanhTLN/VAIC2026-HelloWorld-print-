from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.brand import Brand
from schemas.brand import BrandCreate, BrandUpdate


class BrandRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: BrandCreate) -> Brand:
        brand = Brand(name=data.name)
        self.session.add(brand)
        await self.session.commit()
        await self.session.refresh(brand)
        return brand

    async def get_by_id(self, brand_id: int) -> Brand | None:
        return await self.session.get(Brand, brand_id)

    async def get_by_name(self, name: str) -> Brand | None:
        result = await self.session.execute(select(Brand).where(Brand.name == name))
        return result.scalar_one_or_none()

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[Brand]:
        result = await self.session.execute(
            select(Brand).order_by(Brand.id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def update(self, brand: Brand, data: BrandUpdate) -> Brand:
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(brand, key, value)
        await self.session.commit()
        await self.session.refresh(brand)
        return brand

    async def delete(self, brand: Brand) -> None:
        await self.session.delete(brand)
        await self.session.commit()
