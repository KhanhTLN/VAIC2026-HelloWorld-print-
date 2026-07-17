from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.product import Product
from schemas.product import ProductCreate, ProductUpdate


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: ProductCreate) -> Product:
        product = Product(**data.model_dump())
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def get_by_id(self, product_id: int) -> Product | None:
        return await self.session.get(Product, product_id)

    async def get_by_sku(self, sku: str) -> Product | None:
        result = await self.session.execute(select(Product).where(Product.sku == sku))
        return result.scalar_one_or_none()

    async def search_by_name(self, query: str, *, limit: int = 5) -> list[Product]:
        pattern = f"%{query.strip()}%"
        result = await self.session.execute(
            select(Product)
            .where(
                or_(
                    Product.name.ilike(pattern),
                    Product.model_code.ilike(pattern),
                    Product.sku.ilike(pattern),
                )
            )
            .order_by(Product.rating.desc().nulls_last())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        category_id: int | None = None,
        brand_id: int | None = None,
    ) -> list[Product]:
        stmt = select(Product).order_by(Product.id)
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if brand_id is not None:
            stmt = stmt.where(Product.brand_id == brand_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, product: Product, data: ProductUpdate) -> Product:
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(product, key, value)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def delete(self, product: Product) -> None:
        await self.session.delete(product)
        await self.session.commit()
