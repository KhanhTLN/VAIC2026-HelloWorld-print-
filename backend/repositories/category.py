from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.category import Category
from schemas.category import CategoryCreate, CategoryUpdate


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: CategoryCreate) -> Category:
        category = Category(**data.model_dump())
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def get_by_id(self, category_id: int) -> Category | None:
        return await self.session.get(Category, category_id)

    async def get_by_code(self, category_code: str) -> Category | None:
        result = await self.session.execute(
            select(Category).where(Category.category_code == category_code)
        )
        return result.scalar_one_or_none()

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[Category]:
        result = await self.session.execute(
            select(Category).order_by(Category.id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def update(self, category: Category, data: CategoryUpdate) -> Category:
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(category, key, value)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def delete(self, category: Category) -> None:
        await self.session.delete(category)
        await self.session.commit()
