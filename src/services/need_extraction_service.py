from __future__ import annotations

import re
from typing import Any

from src.schemas.workflow import NeedExtraction
from src.utils.llm_client import call_llm_json


class NeedExtractionService:
    def extract(self, user_message: str, history: list[dict[str, str]] | None = None) -> NeedExtraction:
        llm_need = self._extract_with_llm(user_message, history or [])
        if llm_need is not None:
            return llm_need
        return self._fallback_need(user_message)

    def coerce_need(self, payload: dict[str, Any], user_message: str) -> NeedExtraction:
        payload = dict(payload)
        payload["raw_query"] = user_message
        normalized_filters = payload.get("filters") or {}
        if "max_price" in payload:
            normalized_filters.setdefault("max_price", payload["max_price"])
        payload["filters"] = normalized_filters
        return NeedExtraction.model_validate(payload)

    def _extract_with_llm(self, user_message: str, history: list[dict[str, str]]) -> NeedExtraction | None:
        system_prompt = """
Bạn là bộ trích xuất nhu cầu cho backend mua sắm.
Chỉ trả về DUY NHẤT JSON hợp lệ theo schema:
{
  "intent": "search_product|compare_products|recommend|policy_question|general_query",
  "category": "string|null",
  "brand": "string|null",
  "products": ["string"],
  "use_case": "string|null",
  "filters": {
    "min_price": number?,
    "max_price": number?,
    "specifications": object?
  }
}
Không thêm giải thích.
""".strip()
        try:
            payload = call_llm_json(
                system_prompt=system_prompt,
                messages=[*history, {"role": "user", "content": user_message}],
                timeout=20,
            )
            return self.coerce_need(payload, user_message)
        except Exception:
            return None

    def _fallback_need(self, user_message: str) -> NeedExtraction:
        text = user_message.lower()
        intent = "search_product"
        if any(k in text for k in ["so sánh", "compare"]):
            intent = "compare_products"
        elif any(k in text for k in ["gợi ý", "recommend", "best", "phù hợp"]):
            intent = "recommend"
        elif any(k in text for k in ["chính sách", "bảo hành", "đổi trả", "trả góp"]):
            intent = "policy_question"

        filters: dict[str, Any] = {}
        budget_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:tr|triệu)", text)
        if budget_match:
            filters["max_price"] = int(float(budget_match.group(1).replace(",", ".")) * 1_000_000)

        category = None
        if "laptop" in text:
            category = "Laptop"
        elif "điện thoại" in text or "iphone" in text:
            category = "Điện thoại"
        elif "tủ lạnh" in text:
            category = "Tủ lạnh"
        elif "máy lạnh" in text or "điều hòa" in text:
            category = "Máy lạnh"

        products = []
        if intent == "compare_products":
            chunks = [part.strip() for part in re.split(r"và|,", user_message) if part.strip()]
            products = chunks[:2]

        return NeedExtraction(
            intent=intent,
            category=category,
            products=products,
            filters=filters,
            raw_query=user_message,
        )
