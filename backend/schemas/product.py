from datetime import datetime
from decimal import Decimal
from math import isnan
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1)
    sku: str | None = Field(default=None, max_length=100)
    model_code: str | None = Field(default=None, max_length=100)
    product_id_web: str | None = Field(default=None, max_length=100)
    category_id: int | None = None
    brand_id: int | None = None
    description: str | None = None
    original_price: Decimal | None = Field(default=None, ge=0)
    sale_price: Decimal | None = Field(default=None, ge=0)
    gift_promotion: str | None = None
    thumbnail: str | None = None
    rating: Decimal | None = Field(default=Decimal("0"), ge=0, le=5)
    review_count: int | None = Field(default=0, ge=0)
    stock: int | None = Field(default=0, ge=0)
    specifications: dict[str, Any] = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    sku: str | None = Field(default=None, max_length=100)
    model_code: str | None = Field(default=None, max_length=100)
    product_id_web: str | None = Field(default=None, max_length=100)
    category_id: int | None = None
    brand_id: int | None = None
    description: str | None = None
    original_price: Decimal | None = Field(default=None, ge=0)
    sale_price: Decimal | None = Field(default=None, ge=0)
    gift_promotion: str | None = None
    thumbnail: str | None = None
    rating: Decimal | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    specifications: dict[str, Any] | None = None


def _finite_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            return None
        return value
    if isinstance(value, float) and isnan(value):
        return None
    return Decimal(str(value))


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sku: str | None
    model_code: str | None
    product_id_web: str | None
    category_id: int | None
    brand_id: int | None
    description: str | None
    original_price: Decimal | None
    sale_price: Decimal | None
    gift_promotion: str | None
    thumbnail: str | None
    rating: Decimal | None
    review_count: int | None
    stock: int | None
    specifications: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("original_price", "sale_price", "rating", mode="before")
    @classmethod
    def sanitize_decimals(cls, value: Any) -> Decimal | None:
        return _finite_decimal(value)
