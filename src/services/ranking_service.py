from __future__ import annotations

from src.models.product import ProductRecord, RankedProduct
from src.schemas.workflow import SearchFilters


class RankingService:
    """
    Deterministic ranking — LLM NEVER ranks.

    Weights (system prompt):
    - Requirement Matching 40%
    - Price 20%
    - Rating 15%
    - Promotion 10%
    - Popularity 10%
    - Availability 5%
    """

    def __init__(self):
        self.weights = {
            "requirement_matching": 0.40,
            "price": 0.20,
            "rating": 0.15,
            "promotion": 0.10,
            "popularity": 0.10,
            "availability": 0.05,
        }

    def rank(
        self,
        products: list[ProductRecord],
        filters: SearchFilters,
        top_k: int = 5,
    ) -> list[RankedProduct]:
        ranked: list[RankedProduct] = []
        for product in products:
            breakdown = {
                "requirement_matching": self._requirement_score(product, filters),
                "price": self._price_score(product, filters),
                "rating": min(max(product.rating, 0.0) / 5.0, 1.0),
                "promotion": self._promotion_score(product),
                "popularity": min(max(product.quantity_sold or product.review_count, 0) / 500.0, 1.0),
                "availability": 1.0 if (product.quantity_sold or product.stock or 0) > 0 else 0.2,
            }
            final_score = sum(breakdown[key] * self.weights[key] for key in breakdown)
            ranked.append(
                RankedProduct(
                    product=product,
                    score=round(final_score, 6),
                    breakdown=breakdown,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _price_score(product: ProductRecord, filters: SearchFilters) -> float:
        if filters.max_price is None:
            return 0.6
        if product.sale_price <= 0:
            return 0.3
        if product.sale_price <= filters.max_price:
            ratio = product.sale_price / max(filters.max_price, 1)
            return 0.55 + 0.45 * ratio
        overshoot = product.sale_price - filters.max_price
        ratio = overshoot / max(filters.max_price, 1)
        return max(0.0, 1.0 - ratio)

    @staticmethod
    def _promotion_score(product: ProductRecord) -> float:
        text = (product.promotion or product.gift_promotion or "").strip()
        if not text:
            return 0.2
        return 1.0

    @staticmethod
    def _requirement_score(product: ProductRecord, filters: SearchFilters) -> float:
        score = 0.5
        parts = 0
        matched = 0

        if filters.brand:
            parts += 1
            if product.brand and filters.brand.lower() in product.brand.lower():
                matched += 1

        if filters.category:
            parts += 1
            if product.category and filters.category.lower() in product.category.lower():
                matched += 1

        spec_filters = filters.specifications or {}
        for key, target in spec_filters.items():
            parts += 1
            actual = product.specifications.get(key)
            if actual is None:
                # fuzzy key match
                key_l = key.lower()
                for pk, pv in product.specifications.items():
                    if key_l in pk.lower() or pk.lower() in key_l:
                        actual = pv
                        break
            if actual is None:
                continue
            if isinstance(target, dict):
                try:
                    val = float(str(actual).replace(",", ".").split()[0])
                except (TypeError, ValueError, IndexError):
                    continue
                low = target.get("min")
                high = target.get("max")
                if low is not None and val < float(low):
                    continue
                if high is not None and val > float(high):
                    continue
                matched += 1
            elif isinstance(target, (int, float)):
                actual_s = str(actual).lower()
                if str(target) in actual_s:
                    matched += 1
                else:
                    try:
                        digits = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in actual_s)
                        num = float(digits.split()[0]) if digits.split() else None
                        if num is not None and num >= float(target):
                            matched += 1
                    except (TypeError, ValueError, IndexError):
                        pass
            else:
                if str(target).lower() in str(actual).lower():
                    matched += 1

        if parts == 0:
            return 0.6
        return matched / parts
