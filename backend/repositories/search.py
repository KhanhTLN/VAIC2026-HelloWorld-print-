from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement
from sqlalchemy.types import Numeric, String

from models.product import Product
from schemas.search import FilterCondition, FilterOperator


METADATA_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "sku",
        "model_code",
        "stock",
        "rating",
        "review_count",
        "original_price",
        "sale_price",
    }
)


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _effective_price(self) -> ColumnElement[Any]:
        return func.coalesce(Product.sale_price, Product.original_price)

    def _apply_metadata_filter(
        self,
        condition: FilterCondition,
    ) -> ColumnElement[bool]:
        column = getattr(Product, condition.field)
        op = condition.operator
        value = condition.value

        if op == FilterOperator.EQ:
            return column == value
        if op == FilterOperator.GT:
            return column > value
        if op == FilterOperator.GTE:
            return column >= value
        if op == FilterOperator.LT:
            return column < value
        if op == FilterOperator.LTE:
            return column <= value
        if op == FilterOperator.LIKE:
            return cast(column, String).ilike(f"%{value}%")
        raise ValueError(f"Unsupported operator: {op}")

    def _apply_jsonb_filter(
        self,
        condition: FilterCondition,
    ) -> ColumnElement[bool]:
        jsonb_text = Product.specifications[condition.field].astext
        op = condition.operator
        value = condition.value

        if op == FilterOperator.LIKE:
            return jsonb_text.ilike(f"%{value}%")

        if op == FilterOperator.EQ:
            if isinstance(value, bool):
                return jsonb_text == ("true" if value else "false")
            text_value = str(value)
            # Prefer text match — many imported specs store units (e.g. "200 Lít").
            return or_(
                jsonb_text == text_value,
                jsonb_text.ilike(f"{text_value}%"),
                jsonb_text.ilike(f"%{text_value}%"),
            )

        numeric_expr = cast(jsonb_text, Numeric)
        if op == FilterOperator.GT:
            return numeric_expr > value
        if op == FilterOperator.GTE:
            return numeric_expr >= value
        if op == FilterOperator.LT:
            return numeric_expr < value
        if op == FilterOperator.LTE:
            return numeric_expr <= value
        raise ValueError(f"Unsupported operator: {op}")

    def _jsonb_clause(self, condition: FilterCondition) -> ColumnElement[bool]:
        return and_(
            Product.specifications.has_key(condition.field),
            self._apply_jsonb_filter(condition),
        )

    def _build_base_query(
        self,
        *,
        category_id: int | None,
        brand_id: int | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        filters: list[FilterCondition],
        or_filter_groups: list[list[FilterCondition]],
        jsonb_fields: set[str],
    ) -> Select[tuple[Product]]:
        stmt = select(Product)
        clauses: list[ColumnElement[bool]] = []

        if category_id is not None:
            clauses.append(Product.category_id == category_id)
        if brand_id is not None:
            clauses.append(Product.brand_id == brand_id)

        price = self._effective_price()
        if min_price is not None:
            clauses.append(price >= min_price)
        if max_price is not None:
            clauses.append(price <= max_price)

        for condition in filters:
            if condition.field in METADATA_FIELDS:
                clauses.append(self._apply_metadata_filter(condition))
            elif condition.field in jsonb_fields:
                clauses.append(self._jsonb_clause(condition))
            else:
                raise ValueError(f"Unsupported filter field: {condition.field}")

        for group in or_filter_groups:
            group_clauses = [
                self._jsonb_clause(condition)
                for condition in group
                if condition.field in jsonb_fields
            ]
            if group_clauses:
                clauses.append(or_(*group_clauses))

        if clauses:
            stmt = stmt.where(and_(*clauses))
        return stmt

    async def search(
        self,
        *,
        category_id: int | None,
        brand_id: int | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        filters: list[FilterCondition],
        or_filter_groups: list[list[FilterCondition]] | None = None,
        jsonb_fields: set[str],
        skip: int,
        limit: int,
    ) -> tuple[list[Product], int]:
        base = self._build_base_query(
            category_id=category_id,
            brand_id=brand_id,
            min_price=min_price,
            max_price=max_price,
            filters=filters,
            or_filter_groups=or_filter_groups or [],
            jsonb_fields=jsonb_fields,
        )

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        result = await self.session.execute(
            base.order_by(Product.id).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_bestsellers(
        self,
        *,
        category_id: int | None,
        limit: int = 5,
    ) -> list[Product]:
        stmt = select(Product)
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)

        stmt = stmt.order_by(
            Product.rating.desc().nulls_last(),
            Product.review_count.desc().nulls_last(),
            Product.id.asc(),
        ).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
