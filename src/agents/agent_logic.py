from __future__ import annotations

from collections.abc import Generator

from src.services.need_extraction_service import NeedExtractionService
from src.services.workflow_service import WorkflowService
from src.utils.llm_client import call_llm_stream

_workflow_service = WorkflowService()
_need_service = NeedExtractionService()


def call_local_llm_stream(system_prompt, messages):
    """Backward-compatible adapter for streaming LLM output."""
    return call_llm_stream(system_prompt=system_prompt, messages=messages)


def analyze_intent_fast(user_message):
    """Backward-compatible adapter that now returns validated structured need."""
    need = _need_service.extract(user_message=user_message, history=[])
    return {
        "intent": need.intent,
        "category": need.category,
        "brand": need.brand,
        "products": need.products,
        "use_case": need.use_case,
        "filters": need.filters,
        "raw_query": need.raw_query,
    }


def db_search_products(category, budget, user_message):
    """Backward-compatible shim returning context text from ranked products."""
    need_payload = {
        "intent": "search_product",
        "category": category,
        "filters": {},
    }
    if budget:
        need_payload["filters"]["max_price"] = budget

    need = _need_service.coerce_need(need_payload, user_message=user_message)
    filters, candidates = _workflow_service.search_service.search(need=need, user_message=user_message)
    ranked = _workflow_service.ranking_service.rank(candidates, filters, top_k=3)

    lines = []
    for item in ranked:
        p = item.product
        lines.append(
            f"Sản phẩm: {p.name}. Thương hiệu: {p.brand or 'Khác'}. "
            f"Ngành hàng: {p.category or 'Khác'}. Giá: {p.sale_price}. "
            f"Thông số: {p.specifications}. Khuyến mãi: {p.gift_promotion or 'Không có'}."
        )
    context = "\n".join(lines)
    top_relevance = ranked[0].product.relevance if ranked else 0
    return context, False, top_relevance


def generate_advisor_response_stream(user_message, history=None) -> Generator[str, None, None]:
    """Thin orchestrator: intent extraction -> backend search/ranking/tradeoff -> LLM response."""
    for chunk in _workflow_service.run_stream(user_message=user_message, history=history):
        yield chunk
