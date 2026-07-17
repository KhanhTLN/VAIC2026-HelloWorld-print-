from sqlalchemy.ext.asyncio import AsyncSession

from schemas.assist import AssistRequest, AssistResponse
from schemas.search import SearchRequest
from services.mvp import build_tradeoffs, generate_answer, rank_products
from services.search import SearchService


class AssistService:
    """MVP orchestrator: Search → Rank → Trade-off → Response."""

    def __init__(self, session: AsyncSession) -> None:
        self.search_service = SearchService(session)

    async def assist(self, request: AssistRequest) -> AssistResponse:
        payload = request.model_dump(exclude={"top_n"})
        payload["skip"] = 0
        payload["limit"] = min(request.limit, 100)
        search_req = SearchRequest.model_validate(payload)
        search_result = await self.search_service.search(search_req)

        need = {
            "category": request.category,
            "brand": request.brand,
            "min_price": (
                str(request.min_price) if request.min_price is not None else None
            ),
            "max_price": (
                str(request.max_price) if request.max_price is not None else None
            ),
            "filters": [f.model_dump() for f in request.filters],
        }

        if search_result.total == 0:
            answer = generate_answer(
                search_req,
                [],
                [],
                total=0,
                suggestions=search_result.suggestions,
            )
            return AssistResponse(
                need=need,
                candidates_total=0,
                top_products=[],
                tradeoffs=[],
                suggestions=search_result.suggestions,
                answer=answer,
            )

        ranked = rank_products(
            search_result.products,
            search_req,
            top_n=request.top_n,
        )
        tradeoffs = build_tradeoffs(ranked)
        answer = generate_answer(
            search_req,
            ranked,
            tradeoffs,
            total=search_result.total,
        )

        return AssistResponse(
            need=need,
            candidates_total=search_result.total,
            top_products=[product for product, _ in ranked],
            tradeoffs=tradeoffs,
            suggestions=[],
            answer=answer,
        )
