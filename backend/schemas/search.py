from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from schemas.product import ProductRead


class FilterOperator(StrEnum):
    EQ = "eq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    LIKE = "like"


class FilterCondition(BaseModel):
    """Structured filter for metadata columns or JSONB specification keys."""

    field: str = Field(..., min_length=1)
    operator: FilterOperator
    value: Any


_PRICE_KEYS = {
    "min_price": "min_price",
    "minPrice": "min_price",
    "max_price": "max_price",
    "maxPrice": "max_price",
}


class SearchRequest(BaseModel):
    """
    Backend search payload.

    Accepts filters in either form:
    1) Structured: [{"field": "ram", "operator": "eq", "value": 16}]
    2) Shorthand dict: {"ram": 16, "max_price": 25000000}
    3) Shorthand list: [{"ram": "8gb"}]
    """

    category: str | None = Field(
        default=None,
        description="Category name or category_code",
    )
    brand: str | None = Field(default=None, description="Brand name")
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    filters: list[FilterCondition] = Field(default_factory=list)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="before")
    @classmethod
    def normalize_filters(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        raw_filters = payload.get("filters", [])
        conditions: list[dict[str, Any]] = []

        def absorb_shorthand(mapping: dict[str, Any]) -> None:
            for key, value in mapping.items():
                price_field = _PRICE_KEYS.get(key)
                if price_field is not None:
                    if payload.get(price_field) is None:
                        payload[price_field] = value
                    continue
                conditions.append(
                    {
                        "field": key,
                        "operator": FilterOperator.EQ,
                        "value": value,
                    }
                )

        if isinstance(raw_filters, dict):
            absorb_shorthand(raw_filters)
        elif isinstance(raw_filters, list):
            for item in raw_filters:
                if isinstance(item, FilterCondition):
                    conditions.append(item.model_dump())
                    continue
                if not isinstance(item, dict):
                    raise ValueError("Each filter must be an object")
                if "field" in item and "operator" in item:
                    conditions.append(item)
                else:
                    absorb_shorthand(item)
        elif raw_filters is None:
            conditions = []
        else:
            raise ValueError("filters must be a list or an object")

        payload["filters"] = conditions
        return payload


class SearchResponse(BaseModel):
    products: list[ProductRead]
    total: int
    suggestions: list[ProductRead] = Field(default_factory=list)
    message: str | None = None
