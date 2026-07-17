from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.session_store import ChatSession, session_store
from models.brand import Brand
from models.category import Category
from repositories.product import ProductRepository
from repositories.search import SearchRepository
from schemas.chat import ChatRequest, ChatResponse
from schemas.product import ProductRead
from schemas.search import FilterCondition, FilterOperator, SearchRequest, SearchResponse
from services.criteria import (
    META_BRAND,
    META_MAX_PRICE,
    extract_criteria_from_message,
    next_field_to_ask,
    prioritize_ask_fields,
    question_for_field,
)
from services.mvp import build_tradeoffs, generate_answer, rank_products
from services.search import SearchService
from utils.consult_scripts import CategoryTrigger, find_trigger
from utils.spec_dictionary import SpecDictionary


_BUY_INTENT = (
    "muốn mua",
    "muon mua",
    "tìm mua",
    "tim mua",
    "cần mua",
    "can mua",
    "tư vấn",
    "tu van",
    "giúp chọn",
    "giup chon",
    "mua",
)

# Enough volunteered/answered criteria to recommend.
DEFAULT_TARGET_CRITERIA = 2


class ChatService:
    """
    Dynamic consult chat:

    - Criteria are discovered from product.specifications of the category (DB).
    - User may volunteer criteria in any turn (e.g. "tủ lạnh 400l").
    - Bot asks about remaining high-value fields until target_criteria is reached.
    - Naming a product (e.g. iPhone 17 Pro Max) → direct lookup.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.db = session
        self.products = ProductRepository(session)
        self.search_service = SearchService(session)
        self.spec_dictionary = SpecDictionary(session)

    async def handle(self, request: ChatRequest) -> ChatResponse:
        message = request.message.strip()

        if request.session_id:
            existing = session_store.get(request.session_id)
            if existing is not None:
                return await self._continue(existing, message)

        if self._looks_like_product_query(message):
            direct = await self._handle_product_direct(message)
            if direct is not None:
                return direct
            return ChatResponse(
                phase="clarify",
                reply=(
                    f"Mình chưa tìm thấy sản phẩm tên “{message}”. "
                    "Bạn gửi tên khác, hoặc nói ngành hàng (ví dụ: tủ lạnh) để mình tư vấn ạ."
                ),
            )

        trigger = find_trigger(message)
        if trigger is not None or self._has_buy_intent(message):
            return await self._start(message, trigger)

        matches = await self.products.search_by_name(message, limit=3)
        if matches:
            products = [ProductRead.model_validate(p) for p in matches]
            lines = ["Mình tìm thấy vài sản phẩm gần với tên bạn nêu:"]
            for p in products:
                price = p.sale_price or p.original_price
                price_text = f"{price:,.0f}đ" if price is not None else "liên hệ"
                lines.append(f"- {p.name} ({price_text})")
            return ChatResponse(
                phase="product_direct",
                reply="\n".join(lines),
                products=products,
            )

        return ChatResponse(
            phase="clarify",
            reply=(
                "Bạn muốn tư vấn theo ngành hàng (tủ lạnh, máy nước nóng,…) "
                "hay tìm đúng tên sản phẩm ạ?"
            ),
        )

    def _has_buy_intent(self, message: str) -> bool:
        text = message.lower()
        return any(token in text for token in _BUY_INTENT)

    def _looks_like_product_query(self, message: str) -> bool:
        text = message.lower().strip()
        if self._has_buy_intent(text) and find_trigger(text):
            return False
        if find_trigger(text) and len(text.split()) <= 5:
            return False
        brandish = (
            "iphone",
            "samsung",
            "xiaomi",
            "oppo",
            "vivo",
            "sony",
            "lg",
            "toshiba",
            "panasonic",
            "sharp",
            "hitachi",
            "macbook",
            "galaxy",
            "pixel",
        )
        if any(b in text for b in brandish) and not self._has_buy_intent(text):
            return True
        if re.search(r"\d", text) and len(text.split()) >= 2 and not find_trigger(text):
            return True
        return False

    async def _handle_product_direct(self, message: str) -> ChatResponse | None:
        cleaned = message
        for token in _BUY_INTENT:
            cleaned = re.sub(re.escape(token), " ", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split()).strip(" ?!.,")
        if len(cleaned) < 2:
            cleaned = message

        matches = await self.products.search_by_name(cleaned, limit=3)
        if not matches:
            matches = await self.products.search_by_name(message, limit=3)
        if not matches:
            return None

        products = [ProductRead.model_validate(p) for p in matches]
        lines = [f"Mình tìm thấy sản phẩm liên quan tới “{cleaned}”:"]
        for idx, p in enumerate(products, start=1):
            price = p.sale_price or p.original_price
            price_text = f"{price:,.0f}đ" if price is not None else "liên hệ"
            lines.append(f"{idx}. {p.name} — {price_text}")
        return ChatResponse(
            phase="product_direct",
            reply="\n".join(lines),
            products=products,
        )

    async def _resolve_category(
        self,
        trigger: CategoryTrigger | None,
        message: str,
    ) -> Category | None:
        hints: list[str] = []
        if trigger is not None:
            hints.extend(trigger.category_hints)
            hints.extend(trigger.trigger_keywords)
        hints.append(message.lower())

        categories = (
            await self.db.execute(select(Category).order_by(Category.id))
        ).scalars().all()

        best: tuple[int, Category] | None = None
        for hint in hints:
            hint_norm = hint.lower().strip()
            if len(hint_norm) < 2:
                continue
            for cat in categories:
                name = (cat.name or "").lower().strip()
                code = (cat.category_code or "").lower().strip()
                score = -1
                if name == hint_norm or code == hint_norm:
                    score = 100
                elif name.startswith(hint_norm):
                    score = 80
                elif hint_norm in name:
                    score = max(10, 60 - (len(name) - len(hint_norm)))
                if score < 0:
                    continue
                if best is None or score > best[0]:
                    best = (score, cat)
        return best[1] if best else None

    async def _brand_names(self) -> list[str]:
        rows = (await self.db.execute(select(Brand.name).order_by(Brand.name))).all()
        return [r[0] for r in rows if r[0]]

    async def _start(
        self,
        message: str,
        trigger: CategoryTrigger | None,
    ) -> ChatResponse:
        category = await self._resolve_category(trigger, message)
        category_name = (
            category.name.strip()
            if category
            else (trigger.name if trigger else "sản phẩm")
        )
        category_id = category.id if category else None

        spec_keys = sorted(
            await self.spec_dictionary.get_allowed_keys(category_id)
        )
        ask_order = prioritize_ask_fields(spec_keys)

        session = session_store.create(
            category_name=category_name,
            category_id=category_id,
            spec_keys=spec_keys,
            target_criteria=DEFAULT_TARGET_CRITERIA,
        )

        brands = await self._brand_names()
        extracted = await extract_criteria_from_message(
            message,
            spec_keys=spec_keys,
            brand_names=brands,
            pending_field=None,
            spec_dictionary=self.spec_dictionary,
        )
        session.criteria.update(extracted)
        session_store.save(session)

        if len(session.criteria) >= session.target_criteria:
            return await self._recommend(session)

        ask_order = prioritize_ask_fields(spec_keys)
        field = next_field_to_ask(ask_order, session.criteria, session.asked_fields)
        if field is None:
            return await self._recommend(session)
        return self._build_ask_response(session, field, opening=True)

    async def _continue(self, session: ChatSession, message: str) -> ChatResponse:
        brands = await self._brand_names()
        extracted = await extract_criteria_from_message(
            message,
            spec_keys=session.spec_keys,
            brand_names=brands,
            pending_field=session.pending_field,
            spec_dictionary=self.spec_dictionary,
        )
        session.criteria.update(extracted)
        if session.pending_field and session.pending_field not in session.asked_fields:
            session.asked_fields.append(session.pending_field)
        session.pending_field = None
        session_store.save(session)

        if len(session.criteria) >= session.target_criteria:
            return await self._recommend(session)

        ask_order = prioritize_ask_fields(session.spec_keys)
        field = next_field_to_ask(ask_order, session.criteria, session.asked_fields)
        if field is None:
            return await self._recommend(session)
        return self._build_ask_response(session, field, opening=False)

    def _build_ask_response(
        self,
        session: ChatSession,
        field: str,
        *,
        opening: bool,
    ) -> ChatResponse:
        session.pending_field = field
        if field not in session.asked_fields:
            session.asked_fields.append(field)
        session_store.save(session)

        got = len(session.criteria)
        need = session.target_criteria
        question = question_for_field(field)

        if opening:
            reply = (
                f"Bạn đang tìm {session.category_name} phải không ạ?\n"
                f"Mình hỏi theo thông số thực tế của ngành hàng này "
                f"(cần khoảng {need} tiêu chí).\n"
                f"{question}"
            )
        else:
            reply = f"Đã có {got}/{need} tiêu chí.\n{question}"

        if session.criteria:
            summary = ", ".join(f"{k}={v}" for k, v in session.criteria.items())
            reply += f"\n(Hiện có: {summary})"

        return ChatResponse(
            session_id=session.session_id,
            phase="ask",
            reply=reply,
            question_index=got + 1,
            questions_total=need,
            need={"criteria": {k: str(v) for k, v in session.criteria.items()}, "category": session.category_name},
        )

    async def _recommend(self, session: ChatSession) -> ChatResponse:
        criteria = session.criteria
        brand = criteria.get(META_BRAND)
        max_price = criteria.get(META_MAX_PRICE)
        # max_price might be raw string — SearchRequest expects Decimal|None
        from decimal import Decimal, InvalidOperation

        price_value = None
        if max_price is not None:
            try:
                price_value = max_price if isinstance(max_price, Decimal) else Decimal(str(max_price))
            except (InvalidOperation, ValueError):
                price_value = None

        filters = [
            FilterCondition(field=str(k), operator=FilterOperator.EQ, value=v)
            for k, v in criteria.items()
            if k not in {META_BRAND, META_MAX_PRICE, "min_price"}
        ]

        search_req = SearchRequest(
            category=session.category_name,
            brand=str(brand) if brand else None,
            max_price=price_value,
            filters=filters,
            limit=50,
        )
        search_result = await self._safe_search(session, search_req)

        need = {
            "category": session.category_name,
            "criteria": {k: str(v) for k, v in criteria.items()},
        }
        summary = "\n".join(f"- {k}: {v}" for k, v in criteria.items())

        if search_result.total == 0:
            suggestions = search_result.suggestions
            reply = generate_answer(
                search_req, [], [], total=0, suggestions=suggestions
            )
            reply = f"Cảm ơn bạn. Tiêu chí đã có:\n{summary}\n\n{reply}"
            session_store.delete(session.session_id)
            return ChatResponse(
                phase="recommend",
                reply=reply,
                products=suggestions[:3],
                need=need,
            )

        ranked = rank_products(search_result.products, search_req, top_n=3)
        tradeoffs = build_tradeoffs(ranked)
        base = generate_answer(
            search_req, ranked, tradeoffs, total=search_result.total
        )
        reply = (
            f"Cảm ơn bạn. Mình đã có {len(criteria)} tiêu chí:\n{summary}\n\n"
            f"Gợi ý sản phẩm phù hợp:\n{base}"
        )
        session_store.delete(session.session_id)
        return ChatResponse(
            phase="recommend",
            reply=reply,
            products=[p for p, _ in ranked],
            tradeoffs=tradeoffs,
            need=need,
        )

    async def _safe_search(
        self,
        session: ChatSession,
        search_req: SearchRequest,
    ) -> SearchResponse:
        try:
            result = await self.search_service.search(search_req)
            if result.total > 0:
                return result
        except HTTPException:
            pass

        relaxed = SearchRequest(
            category=search_req.category,
            brand=search_req.brand,
            max_price=search_req.max_price,
            filters=[],
            limit=50,
        )
        try:
            result = await self.search_service.search(relaxed)
            if result.total > 0:
                return result
        except HTTPException:
            pass

        repo = SearchRepository(self.db)
        products = await repo.get_bestsellers(
            category_id=session.category_id,
            limit=10,
        )
        reads = [ProductRead.model_validate(p) for p in products]
        if reads:
            return SearchResponse(products=reads, total=len(reads))
        return SearchResponse(
            products=[],
            total=0,
            suggestions=[],
            message="Không tìm thấy sản phẩm phù hợp.",
        )
