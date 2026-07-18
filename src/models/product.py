from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductRecord:
    product_id: str
    name: str
    brand: str | None = None
    category: str | None = None
    category_id: int | None = None
    product_code: str | None = None
    product_type: str | None = None
    color: str | None = None
    sale_price: int = 0
    original_price: int = 0
    rating: float = 0.0
    review_count: int = 0
    quantity_sold: int = 0
    stock: int = 0
    online_sale_only: bool = False
    promotion: str = ""
    outstanding: str = ""
    accessories: str = ""
    warranty_policy: str = ""
    gift_promotion: str = ""  # alias of promotion for older callers
    description: str = ""
    specifications: dict[str, Any] = field(default_factory=dict)  # spec_product
    url_image: str | None = None
    url: str | None = None
    relevance: float = 0.0

    def to_card(self, *, score: float | None = None, breakdown: dict[str, float] | None = None) -> dict[str, Any]:
        """Frontend product card payload — never invent URLs/prices."""
        card: dict[str, Any] = {
            "product_id": self.product_id,
            "product_code": self.product_code,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "color": self.color,
            "sale_price": self.sale_price,
            "original_price": self.original_price or None,
            "promotion": self.promotion or self.gift_promotion or None,
            "rating": self.rating,
            "quantity_sold": self.quantity_sold,
            "outstanding": self.outstanding or None,
            "warranty_policy": self.warranty_policy or None,
            "spec_product": self.specifications,
            "url_image": self.url_image,
            "url": self.url,
        }
        if score is not None:
            card["score"] = score
        if breakdown is not None:
            card["score_breakdown"] = breakdown
        return card


@dataclass
class RankedProduct:
    product: ProductRecord
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)
