from __future__ import annotations

import json
from collections.abc import Generator

from src.models.product import RankedProduct
from src.schemas.workflow import NeedExtraction, TradeoffOutput
from src.utils.llm_client import call_llm_stream


class ResponseService:
    def stream_response(
        self,
        need: NeedExtraction,
        ranked_products: list[RankedProduct],
        tradeoff: TradeoffOutput,
        history: list[dict[str, str]] | None = None,
        policy_chunks: list[str] | None = None,
    ) -> Generator[str, None, None]:
        policy_chunks = policy_chunks or []

        if need.intent == "policy_question" and not policy_chunks:
            yield "Hiện tôi chưa tìm thấy dữ liệu chính sách phù hợp. Anh/chị vui lòng liên hệ tổng đài 1900.232.461 để được hỗ trợ nhanh nhất."
            return

        if not ranked_products and need.intent != "policy_question":
            yield "Hiện chưa có sản phẩm phù hợp bộ lọc của anh/chị trong hệ thống. Anh/chị có thể nới ngân sách hoặc giảm bớt tiêu chí để em tìm lại nhanh hơn."
            return

        response_payload = {
            "intent": need.intent,
            "top_products": [
                {
                    "id": item.product.product_id,
                    "name": item.product.name,
                    "brand": item.product.brand,
                    "category": item.product.category,
                    "sale_price": item.product.sale_price,
                    "gift_promotion": item.product.gift_promotion,
                    "score": item.score,
                    "score_breakdown": item.breakdown,
                    "specifications": item.product.specifications,
                }
                for item in ranked_products
            ],
            "tradeoff": tradeoff.model_dump(),
            "policy": policy_chunks,
        }

        system_prompt = f"""
Bạn là bộ tạo phản hồi tiếng Việt cho trợ lý mua sắm.
Bạn KHÔNG được tự suy luận dữ liệu ngoài payload.
Bạn chỉ diễn đạt tự nhiên từ payload backend sau:
{json.dumps(response_payload, ensure_ascii=False)}
Yêu cầu:
- Nêu ngắn gọn sản phẩm đề xuất.
- Nêu trade-off ưu/nhược theo dữ liệu đã cho.
- Không bịa thông tin sản phẩm, giá, khuyến mãi.
- Trả lời 100% tiếng Việt.
""".strip()

        messages = history or [{"role": "user", "content": need.raw_query}]
        for chunk in call_llm_stream(system_prompt, messages):
            yield chunk
