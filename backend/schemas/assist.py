from typing import Any

from pydantic import BaseModel, Field

from schemas.product import ProductRead
from schemas.search import SearchRequest


class AssistRequest(SearchRequest):
    """Reuse SearchRequest fields; MVP assistant adds top_n only."""

    top_n: int = Field(default=3, ge=1, le=10)


class AssistResponse(BaseModel):
    need: dict[str, Any]
    candidates_total: int
    top_products: list[ProductRead]
    tradeoffs: list[dict[str, Any]]
    suggestions: list[ProductRead] = Field(default_factory=list)
    answer: str
