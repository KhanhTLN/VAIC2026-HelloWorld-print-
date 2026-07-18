from __future__ import annotations

from collections.abc import Generator

from src.database.vector_store import query_policy
from src.repositories.product_repository import ProductRepository
from src.schemas.workflow import ResponsePayload
from src.services.need_extraction_service import NeedExtractionService
from src.services.ranking_service import RankingService
from src.services.response_service import ResponseService
from src.services.search_service import SearchService
from src.services.tradeoff_service import TradeoffService


class WorkflowService:
    def __init__(
        self,
        need_service: NeedExtractionService | None = None,
        search_service: SearchService | None = None,
        ranking_service: RankingService | None = None,
        tradeoff_service: TradeoffService | None = None,
        response_service: ResponseService | None = None,
    ):
        self.need_service = need_service or NeedExtractionService()
        self.search_service = search_service or SearchService(ProductRepository(), enable_vector_rerank=False)
        self.ranking_service = ranking_service or RankingService()
        self.tradeoff_service = tradeoff_service or TradeoffService()
        self.response_service = response_service or ResponseService()

    def _execute(self, user_message: str, history: list[dict[str, str]] | None = None):
        need = self.need_service.extract(user_message=user_message, history=history)
        filters, candidates = self.search_service.search(need=need, user_message=user_message)
        ranked = self.ranking_service.rank(candidates, filters, top_k=3)
        tradeoff = self.tradeoff_service.build(ranked)

        policy_chunks: list[str] = []
        if need.intent == "policy_question":
            policy_chunks = query_policy(user_message, n_results=3) or []

        return need, filters, ranked, tradeoff, policy_chunks

    def run(self, user_message: str, history: list[dict[str, str]] | None = None) -> ResponsePayload:
        need, filters, ranked, tradeoff, policy_chunks = self._execute(user_message, history)

        return ResponsePayload(
            need=need,
            filters=filters,
            top_products=[
                {
                    "product_id": item.product.product_id,
                    "name": item.product.name,
                    "brand": item.product.brand,
                    "category": item.product.category,
                    "sale_price": item.product.sale_price,
                    "score": item.score,
                    "score_breakdown": item.breakdown,
                    "specifications": item.product.specifications,
                    "gift_promotion": item.product.gift_promotion,
                    "stock": item.product.stock,
                }
                for item in ranked
            ],
            tradeoff=tradeoff,
            policy_chunks=policy_chunks,
        )

    def run_stream(self, user_message: str, history: list[dict[str, str]] | None = None) -> Generator[str, None, None]:
        need, _, ranked, tradeoff, policy_chunks = self._execute(user_message, history)
        for chunk in self.response_service.stream_response(
            need=need,
            ranked_products=ranked,
            tradeoff=tradeoff,
            history=history,
            policy_chunks=policy_chunks,
        ):
            yield chunk
