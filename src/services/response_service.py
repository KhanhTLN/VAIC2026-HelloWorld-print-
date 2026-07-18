from __future__ import annotations

import json
from collections.abc import Generator

from src.models.product import RankedProduct
from src.schemas.workflow import ClarificationResult, NeedExtraction, TradeoffOutput
from src.utils.llm_client import call_llm_stream


class ResponseService:
    def stream_response(
        self,
        need: NeedExtraction,
        ranked_products: list[RankedProduct],
        tradeoff: TradeoffOutput,
        history: list[dict[str, str]] | None = None,
        policy_chunks: list[str] | None = None,
        clarification: ClarificationResult | None = None,
        relaxed: bool = False,
    ) -> Generator[str, None, None]:
        policy_chunks = policy_chunks or []

        if clarification is not None and not clarification.ready:
            intro = clarification.message or "Em cần thêm thông tin trước khi tìm sản phẩm."
            yield intro + "\n"
            for idx, question in enumerate(clarification.questions, start=1):
                yield f"{idx}. {question}\n"
            return

        if need.intent in {"policy_question", "warranty_information"} and not policy_chunks and not ranked_products:
            yield (
                "Hiện tôi chưa tìm thấy dữ liệu chính sách phù hợp. "
                "Anh/chị vui lòng liên hệ tổng đài 1900.232.461 để được hỗ trợ nhanh nhất."
            )
            return

        if not ranked_products and need.intent not in {"policy_question", "warranty_information"}:
            yield (
                "Hiện chưa có sản phẩm phù hợp bộ lọc của anh/chị trong hệ thống. "
                "Anh/chị có thể nới ngân sách hoặc giảm bớt tiêu chí để em tìm lại nhanh hơn."
            )
            return

        response_payload = {
            "intent": need.intent,
            "relaxed": relaxed,
            "top_products": [
                item.product.to_card(score=item.score, breakdown=item.breakdown)
                for item in ranked_products
            ],
            "tradeoff": tradeoff.model_dump(),
            "policy": policy_chunks,
        }

        system_prompt = f"""
Bạn là bộ tạo phản hồi tiếng Việt cho trợ lý mua sắm Điện Máy Xanh.
Bạn KHÔNG được tự suy luận / bịa dữ liệu ngoài payload backend.
Bạn chỉ diễn đạt tự nhiên từ payload sau:
{json.dumps(response_payload, ensure_ascii=False)}

Yêu cầu:
- Nếu relaxed=true: nói rõ đây là lựa chọn gần nhất, chưa khớp 100% yêu cầu.
- Với mỗi sản phẩm nêu: tên, giá sale, giá gốc (nếu có), khuyến mãi, rating, điểm nổi bật, vài thông số chính.
- Nhắc có thể xem ảnh/link nếu url_image hoặc url có trong payload (không bịa URL).
- Nêu trade-off ngắn gọn theo dữ liệu.
- Trả lời 100% tiếng Việt.
""".strip()

        messages = history or [{"role": "user", "content": need.raw_query}]
        for chunk in call_llm_stream(system_prompt, messages):
            yield chunk
