import unittest

from src.repositories.product_repository import ProductRepository


class JsonbFilterBuilderTests(unittest.TestCase):
    def test_build_search_query_contains_jsonb_filter(self):
        sql, params = ProductRepository.build_search_query(
            {
                "category": "Laptop",
                "max_price": 20000000,
                "specifications": {"ram": 16, "cpu": "M4"},
            },
            limit=20,
        )

        self.assertIn("jsonb_extract_path_text(p.specifications", sql)
        self.assertIn("p.sale_price <= %s", sql)
        self.assertIn("LIMIT 20", sql)
        self.assertIn("Laptop", params)
        self.assertIn(20000000, params)


if __name__ == "__main__":
    unittest.main()
