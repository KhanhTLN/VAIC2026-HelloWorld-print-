from __future__ import annotations

from src.models.product import ProductRecord, RankedProduct
from src.schemas.workflow import SearchFilters


class RankingService:
    def __init__(self):
        self.weights = {
            "budget": 0.25,
            "specifications": 0.25,
            "popularity": 0.15,
            "rating": 0.15,
            "stock": 0.10,
            "relevance": 0.10,
        }

    def rank(self, products: list[ProductRecord], filters: SearchFilters, top_k: int = 3) -> list[RankedProduct]:
        ranked: list[RankedProduct] = []
        for product in products:
            budget_score = self._budget_score(product, filters)
            spec_score = self._spec_score(product, filters)
            popularity_score = min(max(product.review_count, 0) / 500.0, 1.0)
            rating_score = min(max(product.rating, 0.0) / 5.0, 1.0)
            stock_score = min(max(product.stock, 0) / 50.0, 1.0)
            relevance_score = min(max(product.relevance, 0.0), 1.0)

            breakdown = {
                "budget": budget_score,
                "specifications": spec_score,
                "popularity": popularity_score,
                "rating": rating_score,
                "stock": stock_score,
                "relevance": relevance_score,
            }
            final_score = sum(breakdown[key] * self.weights[key] for key in breakdown)
            ranked.append(RankedProduct(product=product, score=round(final_score, 6), breakdown=breakdown))

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _budget_score(product: ProductRecord, filters: SearchFilters) -> float:
        if filters.max_price is None:
            return 0.6
        if product.sale_price <= filters.max_price:
            return 1.0
        overshoot = product.sale_price - filters.max_price
        ratio = overshoot / max(filters.max_price, 1)
        return max(0.0, 1.0 - ratio)

    @staticmethod
    def _spec_score(product: ProductRecord, filters: SearchFilters) -> float:
        spec_filters = filters.specifications or {}
        if not spec_filters:
            return 0.6

        total = 0
        matched = 0
        for key, target in spec_filters.items():
            total += 1
            actual = product.specifications.get(key)
            if actual is None:
                continue
            if isinstance(target, dict):
                low = target.get("min")
                high = target.get("max")
                try:
                    val = float(actual)
                except (TypeError, ValueError):
                    continue
                if low is not None and val < float(low):
                    continue
                if high is not None and val > float(high):
                    continue
                matched += 1
            elif isinstance(target, (int, float)):
                try:
                    if float(actual) >= float(target):
                        matched += 1
                except (TypeError, ValueError):
                    continue
            else:
                if str(target).lower() in str(actual).lower():
                    matched += 1

        return matched / total if total else 0.0
