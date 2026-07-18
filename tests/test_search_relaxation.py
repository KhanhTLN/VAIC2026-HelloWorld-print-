import unittest
from unittest.mock import MagicMock

from src.models.product import ProductRecord
from src.schemas.workflow import NeedExtraction, SearchFilters
from src.services.search_service import SearchService


class SearchRelaxationTests(unittest.TestCase):
    def test_relaxes_specs_then_brand(self):
        repo = MagicMock()
        # First call (exact) empty, second (after drop RAM) has products
        product = ProductRecord(
            product_id="1",
            name="X",
            brand="Dell",
            category="Laptop",
            sale_price=18000000,
            specifications={"RAM": "8GB"},
        )
        repo.search_candidates.side_effect = [
            [],  # exact
            [product],  # after dropping RAM
        ]
        service = SearchService(repo)
        need = NeedExtraction(
            intent="search_product",
            category="Laptop",
            brand="Dell",
            filters={"max_price": 20000000, "specifications": {"RAM": "16GB"}},
            raw_query="Dell RAM 16 dưới 20tr",
        )
        filters, products, relaxed = service.search(need, need.raw_query)
        self.assertTrue(relaxed)
        self.assertEqual(len(products), 1)
        self.assertNotIn("RAM", filters.specifications)

    def test_no_search_without_category(self):
        repo = MagicMock()
        service = SearchService(repo)
        need = NeedExtraction(intent="search_product", raw_query="tôi muốn mua")
        filters, products, relaxed = service.search(need, need.raw_query)
        self.assertEqual(products, [])
        self.assertFalse(relaxed)
        repo.search_candidates.assert_not_called()


if __name__ == "__main__":
    unittest.main()
