from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.product import ProductRead


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str | None = None
    phase: Literal[
        "ask",
        "recommend",
        "product_direct",
        "clarify",
        "done",
    ]
    reply: str
    question_index: int | None = None
    questions_total: int | None = None
    products: list[ProductRead] = Field(default_factory=list)
    tradeoffs: list[dict[str, Any]] = Field(default_factory=list)
    need: dict[str, Any] | None = None
