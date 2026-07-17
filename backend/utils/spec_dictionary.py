from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.product import Product


def normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


class SpecDictionary:
    """
    Allowed JSONB specification keys, discovered from products in DB.

    Keys are never hardcoded — they come from existing product.specifications
    for the given category (or globally when category is unknown).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_allowed_keys(self, category_id: int | None = None) -> set[str]:
        stmt = select(distinct(func.jsonb_object_keys(Product.specifications)))
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)

        result = await self.session.execute(stmt)
        return {row[0] for row in result.fetchall() if row[0]}

    def resolve_field(self, requested: str, allowed: set[str]) -> list[str]:
        if requested in allowed:
            return [requested]

        requested_norm = normalize_text(requested)
        by_norm = {normalize_text(key): key for key in allowed}
        if requested_norm in by_norm:
            return [by_norm[requested_norm]]

        partial = [
            key
            for key in allowed
            if requested_norm in normalize_text(key) or normalize_text(key) in requested_norm
        ]
        partial.sort(key=lambda key: (len(key), key))
        return partial
