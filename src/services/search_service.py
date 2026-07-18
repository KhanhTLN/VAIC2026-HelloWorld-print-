from __future__ import annotations

import re
from typing import Any

from src.models.product import ProductRecord
from src.repositories.product_repository import ProductRepository
from src.schemas.workflow import NeedExtraction, SearchFilters


class SearchService:
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
            if key in need.filters:
                payload[key] = need.filters[key]
        return SearchFilters.model_validate(payload)

    def search(self, need: NeedExtraction, user_message: str, candidate_limit: int = 30) -> tuple[SearchFilters, list[ProductRecord]]:
        filters = self.build_filters(need)
        if need.intent == "compare_products" and need.products:
            products = self.repository.get_products_by_names(need.products, limit=max(len(need.products), 5))
        elif need.intent in {"search_product", "recommend", "general_query"}:
            products = self.repository.search_candidates(filters.model_dump(), limit=candidate_limit)
        else:
            products = []

        products = self._attach_relevance(products, user_message)
        if self.enable_vector_rerank:
            products = self._optional_vector_rerank(products, user_message)
        return filters, products

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
        # Optional semantic-like reranking hook after PostgreSQL filtering.
        # In local mode this keeps deterministic lexical scoring and can be replaced by real embedding reranking.
        return sorted(products, key=lambda p: (p.relevance, -p.sale_price), reverse=True)
