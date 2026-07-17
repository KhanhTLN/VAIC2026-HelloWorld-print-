from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.category import Category
from repositories.category import CategoryRepository
from schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = CategoryRepository(session)

    async def create(self, data: CategoryCreate) -> Category:
        existing = await self.repo.get_by_code(data.category_code)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category code '{data.category_code}' already exists",
            )
        return await self.repo.create(data)

    async def get(self, category_id: int) -> Category:
        category = await self.repo.get_by_id(category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category id={category_id} not found",
            )
        return category

    async def list(self, *, skip: int = 0, limit: int = 100) -> list[Category]:
        return await self.repo.list(skip=skip, limit=limit)

    async def update(self, category_id: int, data: CategoryUpdate) -> Category:
        category = await self.get(category_id)
        if data.category_code is not None:
            existing = await self.repo.get_by_code(data.category_code)
            if existing is not None and existing.id != category_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Category code '{data.category_code}' already exists",
                )
        return await self.repo.update(category, data)

    async def delete(self, category_id: int) -> None:
        category = await self.get(category_id)
        await self.repo.delete(category)
