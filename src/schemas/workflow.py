from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IntentLiteral = Literal[
    "search_product",
    "compare_products",
    "recommend_product",
    "recommend",  # backward compatible alias
    "product_information",
    "promotion_information",
    "warranty_information",
    "policy_question",
    "general_query",
]


class SearchFilters(BaseModel):
    category: str | None = None
    brand: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    specifications: dict[str, Any] = Field(default_factory=dict)


class NeedExtraction(BaseModel):
    intent: IntentLiteral = "general_query"
    category: str | None = None
    brand: str | None = None
    products: list[str] = Field(default_factory=list)
    use_case: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    raw_query: str = ""


class ClarificationResult(BaseModel):
    ready: bool
    questions: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    searchable_specs: list[str] = Field(default_factory=list)
    message: str | None = None


class RankingInput(BaseModel):
    filters: SearchFilters
    need: NeedExtraction


class TradeoffItem(BaseModel):
    product_name: str
    product_id: str | None = None
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class TradeoffOutput(BaseModel):
    items: list[TradeoffItem] = Field(default_factory=list)
    comparison: list[dict[str, Any]] = Field(default_factory=list)


class ResponsePayload(BaseModel):
    phase: Literal["clarification", "recommendation", "comparison", "information"] = "recommendation"
    need: NeedExtraction
    filters: SearchFilters = Field(default_factory=SearchFilters)
    clarification: ClarificationResult | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    searchable_specs: list[str] = Field(default_factory=list)
    top_products: list[dict[str, Any]] = Field(default_factory=list)
    tradeoff: TradeoffOutput = Field(default_factory=TradeoffOutput)
    policy_chunks: list[str] = Field(default_factory=list)
    relaxed: bool = False
    message: str | None = None
