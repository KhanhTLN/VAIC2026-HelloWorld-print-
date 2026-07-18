import unittest

from src.schemas.workflow import NeedExtraction
from src.services.clarification_service import ClarificationService


class ClarificationServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = ClarificationService()

    def test_requires_category_before_search(self):
        need = NeedExtraction(intent="search_product", raw_query="Tôi cần mua")
        result = self.service.evaluate(need)
        self.assertFalse(result.ready)
        self.assertEqual(result.missing, ["category"])
        self.assertTrue(result.questions)

    def test_ready_when_category_and_budget_present(self):
        need = NeedExtraction(
            intent="search_product",
            category="Laptop",
            filters={"max_price": 20000000},
            raw_query="laptop dưới 20 triệu",
        )
        result = self.service.evaluate(need, searchable_specs=["RAM", "CPU", "Storage"])
        self.assertTrue(result.ready)
        self.assertEqual(result.questions, [])

    def test_asks_at_most_three_questions(self):
        need = NeedExtraction(
            intent="search_product",
            category="Laptop",
            raw_query="Tôi cần mua laptop",
        )
        result = self.service.evaluate(
            need,
            searchable_specs=["RAM", "CPU", "Storage", "GPU", "Battery"],
        )
        self.assertFalse(result.ready)
        self.assertLessEqual(len(result.questions), 3)

    def test_compare_with_products_is_ready(self):
        need = NeedExtraction(
            intent="compare_products",
            products=["iPhone 16", "Galaxy S25"],
            raw_query="so sánh iPhone 16 và Galaxy S25",
        )
        result = self.service.evaluate(need)
        self.assertTrue(result.ready)


if __name__ == "__main__":
    unittest.main()
