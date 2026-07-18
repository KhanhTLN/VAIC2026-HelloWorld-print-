from __future__ import annotations

from collections.abc import Generator

from src.database.vector_store import query_policy
from src.repositories.product_repository import ProductRepository
from src.schemas.workflow import ResponsePayload, SearchFilters
from src.services.clarification_service import ClarificationService
from src.services.need_extraction_service import NeedExtractionService
from src.services.ranking_service import RankingService
from src.services.response_service import ResponseService
from src.services.search_service import SearchService
from src.services.tradeoff_service import TradeoffService


class WorkflowService:
    """
    System workflow (never skip steps):

    User → LLM Need Extraction → Clarification Engine → Search (PostgreSQL)
    → Ranking → Recommendation → Trade-off → LLM NLG
    """

    def __init__(
        self,
        need_service: NeedExtractionService | None = None,
        clarification_service: ClarificationService | None = None,
        search_service: SearchService | None = None,
        ranking_service: RankingService | None = None,
        tradeoff_service: TradeoffService | None = None,
        response_service: ResponseService | None = None,
        repository: ProductRepository | None = None,
    ):
        self.repository = repository or ProductRepository()
        self.need_service = need_service or NeedExtractionService()
        self.clarification_service = clarification_service or ClarificationService()
        self.search_service = search_service or SearchService(
            self.repository, enable_vector_rerank=False
        )
        self.ranking_service = ranking_service or RankingService()
        self.tradeoff_service = tradeoff_service or TradeoffService()
        self.response_service = response_service or ResponseService()

    def _prepare(self, user_message: str, history: list[dict[str, str]] | None = None):
        need = self.need_service.extract(user_message=user_message, history=history)

        categories = []
        try:
            categories = self.repository.list_categories()
        except Exception:
            categories = []
        category_names = [c.get("category_name") for c in categories if c.get("category_name")]

        searchable_specs: list[str] = []
        if need.category:
            try:
                searchable_specs = self.repository.get_searchable_specs(need.category)
            except Exception:
                searchable_specs = []

        clarification = self.clarification_service.evaluate(
            need,
            searchable_specs=searchable_specs,
            category_names=category_names,
        )
        return need, clarification, searchable_specs

    def run(self, user_message: str, history: list[dict[str, str]] | None = None) -> ResponsePayload:
        need, clarification, searchable_specs = self._prepare(user_message, history)

        if not clarification.ready:
            return ResponsePayload(
                phase="clarification",
                need=need,
                clarification=clarification,
                clarification_questions=clarification.questions,
                searchable_specs=searchable_specs,
                message=clarification.message,
            )

        filters, candidates, relaxed = self.search_service.search(
            need=need, user_message=user_message
        )
        ranked = self.ranking_service.rank(candidates, filters, top_k=5)
        tradeoff = self.tradeoff_service.build(ranked)

        policy_chunks: list[str] = []
        if need.intent in {"policy_question", "warranty_information"}:
            try:
                policy_chunks = query_policy(user_message, n_results=3) or []
            except Exception:
                policy_chunks = []

        phase = "recommendation"
        if need.intent == "compare_products":
            phase = "comparison"
        elif need.intent in {
            "product_information",
            "promotion_information",
            "warranty_information",
            "policy_question",
        }:
            phase = "information"

        message = None
        if relaxed and ranked:
            message = (
                "Hiện chưa có sản phẩm đáp ứng 100% yêu cầu, "
                "dưới đây là các lựa chọn gần nhất."
            )
        elif not ranked:
            message = "Không tìm thấy sản phẩm phù hợp trong PostgreSQL."

        return ResponsePayload(
            phase=phase,
            need=need,
            filters=filters,
            clarification=clarification,
            clarification_questions=[],
            searchable_specs=searchable_specs,
            top_products=[
                item.product.to_card(score=item.score, breakdown=item.breakdown)
                for item in ranked
            ],
            tradeoff=tradeoff,
            policy_chunks=policy_chunks,
            relaxed=relaxed,
            message=message,
        )

    def run_stream(
        self, user_message: str, history: list[dict[str, str]] | None = None
    ) -> Generator[str, None, None]:
        need, clarification, _ = self._prepare(user_message, history)

        if not clarification.ready:
            for chunk in self.response_service.stream_response(
                need=need,
                ranked_products=[],
                tradeoff=self.tradeoff_service.build([]),
                history=history,
                clarification=clarification,
            ):
                yield chunk
            return

        filters, candidates, relaxed = self.search_service.search(
            need=need, user_message=user_message
        )
        ranked = self.ranking_service.rank(candidates, filters, top_k=5)
        tradeoff = self.tradeoff_service.build(ranked)

        policy_chunks: list[str] = []
        if need.intent in {"policy_question", "warranty_information"}:
            try:
                policy_chunks = query_policy(user_message, n_results=3) or []
            except Exception:
                policy_chunks = []

        for chunk in self.response_service.stream_response(
            need=need,
            ranked_products=ranked,
            tradeoff=tradeoff,
            history=history,
            policy_chunks=policy_chunks,
            relaxed=relaxed,
        ):
            yield chunk
