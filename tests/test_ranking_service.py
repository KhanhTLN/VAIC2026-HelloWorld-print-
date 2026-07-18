import unittest

from src.models.product import ProductRecord
from src.schemas.workflow import SearchFilters
from src.services.ranking_service import RankingService


class RankingServiceTests(unittest.TestCase):
    def test_rank_prefers_better_budget_and_specs(self):
        service = RankingService()
        filters = SearchFilters(
            max_price=20000000,
            specifications={"ram": 16},
        )
        products = [
            ProductRecord(
                product_id="1",
                name="A",
                sale_price=19000000,
                rating=4.7,
                review_count=300,
                stock=20,
                specifications={"ram": 16},
                relevance=0.8,
            ),
            ProductRecord(
                product_id="2",
                name="B",
                sale_price=23000000,
                rating=4.5,
                review_count=200,
                stock=15,
                specifications={"ram": 8},
                relevance=0.7,
            ),
        ]

        ranked = service.rank(products, filters, top_k=2)

        self.assertEqual(ranked[0].product.product_id, "1")
        self.assertGreater(ranked[0].score, ranked[1].score)


if __name__ == "__main__":
    unittest.main()
