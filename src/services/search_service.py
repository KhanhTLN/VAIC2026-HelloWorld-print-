from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from src.models.product import ProductRecord
from src.repositories.product_repository import ProductRepository
from src.schemas.workflow import NeedExtraction, SearchFilters


class SearchService:
    """
    PostgreSQL is the primary search engine.
    Vector search (if enabled) only re-ranks after SQL filtering.
    """

    def __init__(self, repository: ProductRepository, enable_vector_rerank: bool = False):
        self.repository = repository
        self.enable_vector_rerank = enable_vector_rerank

    def build_filters(self, need: NeedExtraction) -> SearchFilters:
        payload: dict[str, Any] = {
            "category": need.category,
            "brand": need.brand,
            "specifications": {},
        }
        for key in ["min_price", "max_price", "specifications"]:
            if key in (need.filters or {}):
                payload[key] = need.filters[key]

        if not payload.get("specifications"):
            payload["specifications"] = {}
        return SearchFilters.model_validate(payload)

    def search(
        self,
        need: NeedExtraction,
        user_message: str,
        candidate_limit: int = 40,
    ) -> tuple[SearchFilters, list[ProductRecord], bool]:
        """
        Returns (filters_used, products, relaxed).
        """
        filters = self.build_filters(need)

        if need.intent == "compare_products" and need.products:
            products = self.repository.get_products_by_names(
                need.products, limit=max(len(need.products), 5)
            )
            products = self._attach_relevance(products, user_message)
            return filters, products, False

        if need.intent in {
            "product_information",
            "promotion_information",
            "warranty_information",
        } and need.products:
            products = self.repository.get_products_by_names(need.products, limit=5)
            products = self._attach_relevance(products, user_message)
            return filters, products, False

        # Category is mandatory for catalog search.
        if not filters.category:
            return filters, [], False

        products = self.repository.search_candidates(filters.model_dump(), limit=candidate_limit)
        if products:
            products = self._attach_relevance(products, user_message)
            if self.enable_vector_rerank:
                products = self._optional_vector_rerank(products, user_message)
            return filters, products, False

        # No exact match → gradually relax filters.
        relaxed_filters, products = self._relax_until_results(
            filters, candidate_limit=candidate_limit
        )
        products = self._attach_relevance(products, user_message)
        if self.enable_vector_rerank:
            products = self._optional_vector_rerank(products, user_message)
        return relaxed_filters, products, True

    def _relax_until_results(
        self,
        filters: SearchFilters,
        *,
        candidate_limit: int,
    ) -> tuple[SearchFilters, list[ProductRecord]]:
        """
        Relaxation order (system prompt):
        specs → brand → widen price → category-only bestsellers.
        """
        current = filters.model_copy(deep=True)

        # 1) Drop specification filters one by one.
        spec_keys = list((current.specifications or {}).keys())
        for key in spec_keys:
            current.specifications.pop(key, None)
            products = self.repository.search_candidates(
                current.model_dump(), limit=candidate_limit
            )
            if products:
                return current, products

        # 2) Drop brand.
        if current.brand:
            current.brand = None
            products = self.repository.search_candidates(
                current.model_dump(), limit=candidate_limit
            )
            if products:
                return current, products

        # 3) Widen max_price by 30%, then drop price.
        if current.max_price is not None:
            widened = current.model_copy(deep=True)
            widened.max_price = int(current.max_price * 1.3)
            products = self.repository.search_candidates(
                widened.model_dump(), limit=candidate_limit
            )
            if products:
                return widened, products

            current.min_price = None
            current.max_price = None
            products = self.repository.search_candidates(
                current.model_dump(), limit=candidate_limit
            )
            if products:
                return current, products

        # 4) Category only.
        fallback = SearchFilters(category=filters.category, specifications={})
        products = self.repository.search_candidates(
            fallback.model_dump(), limit=candidate_limit
        )
        return fallback, products

    @staticmethod
    def _attach_relevance(products: list[ProductRecord], user_message: str) -> list[ProductRecord]:
        terms = set(re.findall(r"\w+", user_message.lower()))
        if not terms:
            return products
        for product in products:
            haystack = " ".join(
                [
                    product.name.lower(),
                    (product.brand or "").lower(),
                    (product.category or "").lower(),
                    " ".join(f"{k} {v}" for k, v in product.specifications.items()).lower(),
                ]
            )
            tokens = set(re.findall(r"\w+", haystack))
            product.relevance = len(terms.intersection(tokens)) / max(len(terms), 1)
        return products

    @staticmethod
    def _optional_vector_rerank(products: list[ProductRecord], query: str) -> list[ProductRecord]:
        return sorted(products, key=lambda p: (p.relevance, -p.sale_price), reverse=True)
