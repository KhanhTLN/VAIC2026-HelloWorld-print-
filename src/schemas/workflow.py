from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    category: str | None = None
    brand: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    specifications: dict[str, Any] = Field(default_factory=dict)


class NeedExtraction(BaseModel):
    intent: Literal[
        "search_product",
        "compare_products",
        "recommend",
        "policy_question",
        "general_query",
    ] = "general_query"
    category: str | None = None
    brand: str | None = None
    products: list[str] = Field(default_factory=list)
    use_case: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    raw_query: str = ""


class RankingInput(BaseModel):
    filters: SearchFilters
    need: NeedExtraction


class TradeoffItem(BaseModel):
    product_name: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class TradeoffOutput(BaseModel):
    items: list[TradeoffItem] = Field(default_factory=list)


class ResponsePayload(BaseModel):
    need: NeedExtraction
    filters: SearchFilters
    top_products: list[dict[str, Any]] = Field(default_factory=list)
    tradeoff: TradeoffOutput = Field(default_factory=TradeoffOutput)
    policy_chunks: list[str] = Field(default_factory=list)
