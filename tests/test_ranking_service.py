import unittest

from src.models.product import ProductRecord
from src.schemas.workflow import SearchFilters
from src.services.ranking_service import RankingService


class RankingServiceTests(unittest.TestCase):
    def test_rank_prefers_better_requirement_and_price_fit(self):
        service = RankingService()
        filters = SearchFilters(
            category="Laptop",
            brand="Dell",
            max_price=20000000,
            specifications={"RAM": "16GB"},
        )
        products = [
            ProductRecord(
                product_id="1",
                name="A",
                brand="Dell",
                category="Laptop",
                sale_price=19000000,
                rating=4.7,
                quantity_sold=300,
                promotion="Giảm 1 triệu",
                specifications={"RAM": "16GB"},
            ),
            ProductRecord(
                product_id="2",
                name="B",
                brand="Asus",
                category="Laptop",
                sale_price=23000000,
                rating=4.5,
                quantity_sold=200,
                specifications={"RAM": "8GB"},
            ),
        ]

        ranked = service.rank(products, filters, top_k=2)

        self.assertEqual(ranked[0].product.product_id, "1")
        self.assertGreater(ranked[0].score, ranked[1].score)
        self.assertIn("requirement_matching", ranked[0].breakdown)
        self.assertAlmostEqual(sum(service.weights.values()), 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
