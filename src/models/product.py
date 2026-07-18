from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductRecord:
    product_id: str
    name: str
    brand: str | None = None
    category: str | None = None
    sale_price: int = 0
    original_price: int = 0
    rating: float = 0.0
    review_count: int = 0
    stock: int = 0
    gift_promotion: str = ""
    description: str = ""
    specifications: dict[str, Any] = field(default_factory=dict)
    relevance: float = 0.0


@dataclass
class RankedProduct:
    product: ProductRecord
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
