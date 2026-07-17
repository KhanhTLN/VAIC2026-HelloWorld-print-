from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.brand import Brand
from models.category import Category
from repositories.search import METADATA_FIELDS, SearchRepository
from schemas.product import ProductRead
from schemas.search import FilterCondition, SearchRequest, SearchResponse
from utils.spec_dictionary import SpecDictionary


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.search_repo = SearchRepository(session)
        self.spec_dictionary = SpecDictionary(session)

    async def _resolve_category(self, category: str | None) -> Category | None:
        if category is None:
            return None

        result = await self.session.execute(
            select(Category).where(
                or_(
                    func.lower(Category.name) == category.lower(),
                    func.lower(Category.category_code) == category.lower(),
                )
            )
        )
        found = result.scalar_one_or_none()
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category '{category}' not found",
            )
        return found

    async def _resolve_brand(self, brand: str | None) -> Brand | None:
        if brand is None:
            return None

        result = await self.session.execute(
            select(Brand).where(func.lower(Brand.name) == brand.lower())
        )
        found = result.scalar_one_or_none()
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Brand '{brand}' not found",
            )
        return found

    def _resolve_filters(
        self,
        filters: list[FilterCondition],
        allowed_jsonb: set[str],
    ) -> tuple[list[FilterCondition], list[list[FilterCondition]]]:
        """Resolve user field names to real JSONB keys (exact / fuzzy)."""
        resolved: list[FilterCondition] = []
        or_groups: list[list[FilterCondition]] = []
        unknown: list[str] = []

        for condition in filters:
            if condition.field in METADATA_FIELDS:
                resolved.append(condition)
                continue

            matches = self.spec_dictionary.resolve_field(condition.field, allowed_jsonb)
            if not matches:
                unknown.append(condition.field)
                continue

            if len(matches) == 1:
                resolved.append(
                    condition.model_copy(update={"field": matches[0]})
                )
            else:
                or_groups.append(
                    [
                        condition.model_copy(update={"field": key})
                        for key in matches
                    ]
                )

        if unknown:
            raise ValueError(
                f"Unknown specification fields: {unknown}. "
                f"Allowed for this category: {sorted(allowed_jsonb)}"
            )
        return resolved, or_groups

    async def search(self, request: SearchRequest) -> SearchResponse:
        category = await self._resolve_category(request.category)
        brand = await self._resolve_brand(request.brand)

        category_id = category.id if category else None
        brand_id = brand.id if brand else None

        try:
            allowed_jsonb = await self.spec_dictionary.get_allowed_keys(category_id)
            filters, or_groups = self._resolve_filters(request.filters, allowed_jsonb)
            products, total = await self.search_repo.search(
                category_id=category_id,
                brand_id=brand_id,
                min_price=request.min_price,
                max_price=request.max_price,
                filters=filters,
                or_filter_groups=or_groups,
                jsonb_fields=allowed_jsonb,
                skip=request.skip,
                limit=request.limit,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        if total == 0:
            suggestions = await self.search_repo.get_bestsellers(
                category_id=category_id,
                limit=5,
            )
            return SearchResponse(
                products=[],
                total=0,
                suggestions=[ProductRead.model_validate(p) for p in suggestions],
                message=(
                    "Không tìm thấy sản phẩm phù hợp. "
                    "Gợi ý một số sản phẩm bán chạy cùng ngành hàng."
                ),
            )

        return SearchResponse(
            products=[ProductRead.model_validate(p) for p in products],
            total=total,
            suggestions=[],
            message=None,
        )
