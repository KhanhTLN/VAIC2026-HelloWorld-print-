import unittest

from src.services.need_extraction_service import NeedExtractionService


class NeedExtractionValidationTests(unittest.TestCase):
    def setUp(self):
        self.service = NeedExtractionService()

    def test_coerce_need_sets_raw_query_and_filters(self):
        payload = {
            "intent": "search_product",
            "category": "Laptop",
            "max_price": 20000000,
            "filters": {"specifications": {"ram": 16}},
        }

        need = self.service.coerce_need(payload, "Laptop 16GB RAM")

        self.assertEqual(need.raw_query, "Laptop 16GB RAM")
        self.assertEqual(need.filters["max_price"], 20000000)
        self.assertEqual(need.filters["specifications"]["ram"], 16)


if __name__ == "__main__":
    unittest.main()
