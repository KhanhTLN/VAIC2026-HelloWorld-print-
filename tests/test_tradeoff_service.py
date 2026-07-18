import unittest

from src.models.product import ProductRecord, RankedProduct
from src.services.tradeoff_service import TradeoffService


class TradeoffServiceTests(unittest.TestCase):
    def test_tradeoff_contains_pros_and_cons(self):
        service = TradeoffService()
        ranked = [
            RankedProduct(
                product=ProductRecord(
                    product_id="1",
                    name="Prod A",
                    sale_price=10000000,
                    rating=4.8,
                    quantity_sold=30,
                    stock=30,
                    promotion="Giảm 500k",
                    specifications={"ram": 16},
                ),
                score=0.9,
            ),
            RankedProduct(
                product=ProductRecord(
                    product_id="2",
                    name="Prod B",
                    sale_price=14000000,
                    rating=4.2,
                    quantity_sold=10,
                    stock=10,
                    specifications={"ram": 8},
                ),
                score=0.8,
            ),
        ]

        output = service.build(ranked)

        self.assertEqual(len(output.items), 2)
        self.assertTrue(output.items[0].pros)
        self.assertTrue(output.comparison)
        self.assertTrue(output.items[1].cons)


if __name__ == "__main__":
    unittest.main()
