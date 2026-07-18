from __future__ import annotations

import re
from typing import Any

from src.schemas.workflow import NeedExtraction
from src.utils.llm_client import call_llm_json


_INTENT_ALIASES = {
    "recommend": "recommend_product",
    "recommend_product": "recommend_product",
    "search_product": "search_product",
    "compare_products": "compare_products",
    "product_information": "product_information",
    "promotion_information": "promotion_information",
    "warranty_information": "warranty_information",
    "policy_question": "policy_question",
    "general_query": "general_query",
}


class NeedExtractionService:
    def extract(self, user_message: str, history: list[dict[str, str]] | None = None) -> NeedExtraction:
        llm_need = self._extract_with_llm(user_message, history or [])
        if llm_need is not None:
            return llm_need
        return self._fallback_need(user_message)

    def coerce_need(self, payload: dict[str, Any], user_message: str) -> NeedExtraction:
        payload = dict(payload)
        payload["raw_query"] = user_message

        intent = str(payload.get("intent") or "general_query")
        payload["intent"] = _INTENT_ALIASES.get(intent, intent)

        normalized_filters = dict(payload.get("filters") or {})
        if "max_price" in payload and "max_price" not in normalized_filters:
            normalized_filters["max_price"] = payload["max_price"]
        if "min_price" in payload and "min_price" not in normalized_filters:
            normalized_filters["min_price"] = payload["min_price"]
        if "requirements" in payload and isinstance(payload["requirements"], dict):
            req = payload["requirements"]
            if "max_price" in req:
                normalized_filters.setdefault("max_price", req["max_price"])
            specs = {k: v for k, v in req.items() if k not in {"max_price", "min_price"}}
            if specs:
                existing = dict(normalized_filters.get("specifications") or {})
                existing.update(specs)
                normalized_filters["specifications"] = existing
        payload["filters"] = normalized_filters
        return NeedExtraction.model_validate(payload)

    def _extract_with_llm(self, user_message: str, history: list[dict[str, str]]) -> NeedExtraction | None:
        system_prompt = """
Bạn là bộ trích xuất nhu cầu (Need Extraction) cho AI Shopping Assistant.
Chỉ trả về DUY NHẤT JSON hợp lệ theo schema:
{
  "intent": "search_product|compare_products|recommend_product|product_information|promotion_information|warranty_information|policy_question|general_query",
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
Quy tắc:
- category phải là ngành hàng (Laptop, Điện thoại, Tủ lạnh...), không phải tên model.
- specifications chỉ chứa thông số kỹ thuật (RAM, CPU, dung tích...).
- Không viết SQL. Không bịa sản phẩm.
- Không thêm giải thích ngoài JSON.
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
        elif any(k in text for k in ["gợi ý", "recommend", "phù hợp nhất"]):
            intent = "recommend_product"
        elif any(k in text for k in ["khuyến mãi", "promotion", "giảm giá"]):
            intent = "promotion_information"
        elif any(k in text for k in ["bảo hành", "warranty"]):
            intent = "warranty_information"
        elif any(k in text for k in ["chính sách", "đổi trả", "trả góp"]):
            intent = "policy_question"

        filters: dict[str, Any] = {}
        budget_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:tr|triệu)", text)
        if budget_match:
            filters["max_price"] = int(float(budget_match.group(1).replace(",", ".")) * 1_000_000)

        specs: dict[str, Any] = {}
        ram_match = re.search(r"ram\s*(\d+)\s*(?:gb)?", text)
        if ram_match:
            specs["RAM"] = f"{ram_match.group(1)}GB"
        liters = re.search(r"(\d+)\s*(?:lít|lit|l)\b", text)
        if liters:
            specs["Dung tích"] = liters.group(1)
        if specs:
            filters["specifications"] = specs

        category = None
        mapping = [
            (("laptop", "máy tính xách tay"), "Laptop"),
            (("điện thoại", "smartphone", "iphone"), "Điện thoại"),
            (("tủ lạnh", "tủ mát", "tủ đông"), "Tủ lạnh"),
            (("máy lạnh", "điều hòa"), "Máy lạnh"),
            (("máy giặt",), "Máy giặt"),
            (("tivi", "television", "tv "), "Tivi"),
            (("máy nước nóng", "bình nóng lạnh"), "Máy nước nóng"),
            (("máy rửa chén", "máy rửa bát"), "Máy rửa chén"),
        ]
        for keys, label in mapping:
            if any(k in text for k in keys):
                category = label
                break

        brand = None
        for b in ("dell", "asus", "apple", "samsung", "lg", "sony", "panasonic", "xiaomi", "oppo", "vivo", "toshiba", "sharp"):
            if b in text:
                brand = b.title() if b != "lg" else "LG"
                if b == "iphone" or (b == "apple" and "iphone" in text):
                    brand = "Apple"
                break

        products: list[str] = []
        if intent == "compare_products":
            chunks = [part.strip() for part in re.split(r"\bvà\b|,| vs ", user_message, flags=re.I) if part.strip()]
            products = chunks[:2]

        return NeedExtraction(
            intent=intent,
            category=category,
            brand=brand,
            products=products,
            filters=filters,
            raw_query=user_message,
        )
