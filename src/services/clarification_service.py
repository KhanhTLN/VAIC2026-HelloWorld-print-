from __future__ import annotations

from src.schemas.workflow import ClarificationResult, NeedExtraction


class ClarificationService:
    """
    Clarification Engine (backend, deterministic).

    - Category MUST be known before search.
    - Ask at most THREE questions.
    - Never ask for information already provided.
    - Spec question candidates come from searchable JSONB keys of the category.
    """

    MAX_QUESTIONS = 3

    def evaluate(
        self,
        need: NeedExtraction,
        *,
        searchable_specs: list[str] | None = None,
        category_names: list[str] | None = None,
    ) -> ClarificationResult:
        searchable_specs = searchable_specs or []
        category_names = category_names or []

        # Compare / named product lookup can proceed without category.
        if need.intent == "compare_products" and need.products:
            return ClarificationResult(ready=True, searchable_specs=searchable_specs)

        if need.intent in {
            "product_information",
            "promotion_information",
            "warranty_information",
        } and need.products:
            return ClarificationResult(ready=True, searchable_specs=searchable_specs)

        if not need.category:
            return ClarificationResult(
                ready=False,
                questions=["Anh/chị đang muốn tìm sản phẩm nào?"],
                missing=["category"],
                searchable_specs=searchable_specs,
                message="Cần xác định ngành hàng trước khi tìm kiếm trong PostgreSQL.",
            )

        # Enough info already → search immediately.
        if self._has_enough_requirements(need):
            return ClarificationResult(
                ready=True,
                searchable_specs=searchable_specs,
                message=None,
            )

        questions: list[str] = []
        missing: list[str] = []
        filters = need.filters or {}
        specs = filters.get("specifications") or {}

        # Priority 1: Budget
        if filters.get("max_price") is None and filters.get("min_price") is None:
            questions.append("Ngân sách khoảng bao nhiêu ạ?")
            missing.append("budget")

        # Priority 2: Usage
        if not need.use_case and len(questions) < self.MAX_QUESTIONS:
            questions.append(self._usage_question(need.category))
            missing.append("use_case")

        # Priority 3: Brand or important specs from JSONB dictionary
        if len(questions) < self.MAX_QUESTIONS and not need.brand:
            questions.append("Có ưu tiên hãng nào không ạ?")
            missing.append("brand")

        for key in self._pick_important_specs(searchable_specs):
            if len(questions) >= self.MAX_QUESTIONS:
                break
            if key in specs:
                continue
            questions.append(f"Anh/chị có yêu cầu gì về “{key}” không?")
            missing.append(key)

        questions = questions[: self.MAX_QUESTIONS]
        missing = missing[: self.MAX_QUESTIONS]

        if not questions:
            return ClarificationResult(ready=True, searchable_specs=searchable_specs)

        hint = ""
        if category_names:
            sample = ", ".join(category_names[:8])
            hint = f" (ví dụ ngành hàng: {sample}…)" if not need.category else ""

        return ClarificationResult(
            ready=False,
            questions=questions,
            missing=missing,
            searchable_specs=searchable_specs,
            message=(
                "Em cần thêm vài thông tin để tìm đúng sản phẩm trong hệ thống."
                + hint
            ),
        )

    @staticmethod
    def _has_enough_requirements(need: NeedExtraction) -> bool:
        """Category + at least one concrete requirement → ready to search."""
        if not need.category:
            return False
        filters = need.filters or {}
        specs = filters.get("specifications") or {}
        if filters.get("max_price") is not None or filters.get("min_price") is not None:
            return True
        if need.brand:
            return True
        if specs:
            return True
        if need.use_case:
            return True
        if need.products:
            return True
        return False

    @staticmethod
    def _usage_question(category: str) -> str:
        text = (category or "").lower()
        if "laptop" in text or "máy tính" in text:
            return "Chủ yếu dùng để học tập, lập trình, gaming hay thiết kế ạ?"
        if "điện thoại" in text or "phone" in text:
            return "Anh/chị ưu tiên chụp ảnh, chơi game hay dùng pin lâu ạ?"
        if "tủ lạnh" in text or "tủ mát" in text or "tủ đông" in text:
            return "Dùng cho gia đình khoảng bao nhiêu người, hay phục vụ kinh doanh ạ?"
        if "máy lạnh" in text or "điều hòa" in text:
            return "Phòng khoảng bao nhiêu m² ạ?"
        if "tivi" in text or "television" in text:
            return "Anh/chị cần kích thước khoảng bao nhiêu inch ạ?"
        if "máy giặt" in text:
            return "Gia đình khoảng bao nhiêu người / khối lượng giặt mong muốn ạ?"
        return "Anh/chị dùng sản phẩm này chủ yếu vào mục đích gì ạ?"

    @staticmethod
    def _pick_important_specs(searchable_specs: list[str]) -> list[str]:
        priority_tokens = [
            "ram",
            "cpu",
            "storage",
            "ssd",
            "dung tích",
            "capacity",
            "pin",
            "battery",
            "camera",
            "màn hình",
            "screen",
            "công suất",
            "inverter",
            "số cửa",
            "cánh",
        ]
        scored: list[tuple[int, str]] = []
        for key in searchable_specs:
            norm = key.lower()
            score = 0
            for idx, token in enumerate(priority_tokens):
                if token in norm:
                    score = max(score, 100 - idx)
            if score:
                scored.append((score, key))
        scored.sort(key=lambda item: (-item[0], len(item[1])))
        return [key for _, key in scored[:3]]
