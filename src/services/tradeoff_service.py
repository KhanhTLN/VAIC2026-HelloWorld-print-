from __future__ import annotations

from statistics import mean

from src.models.product import RankedProduct
from src.schemas.workflow import TradeoffItem, TradeoffOutput


class TradeoffService:
    def build(self, ranked_products: list[RankedProduct]) -> TradeoffOutput:
        if not ranked_products:
            return TradeoffOutput(items=[])

        prices = [item.product.sale_price for item in ranked_products]
        ratings = [item.product.rating for item in ranked_products]
        stocks = [item.product.stock for item in ranked_products]

        avg_price = mean(prices)
        avg_rating = mean(ratings)
        avg_stock = mean(stocks)

        items: list[TradeoffItem] = []
        for item in ranked_products:
            product = item.product
            pros: list[str] = []
            cons: list[str] = []

            if product.sale_price <= avg_price:
                pros.append("Giá cạnh tranh hơn các lựa chọn còn lại")
            else:
                cons.append("Giá cao hơn mặt bằng các lựa chọn")

            if product.rating >= avg_rating:
                pros.append("Đánh giá người dùng tốt")
            else:
                cons.append("Điểm đánh giá thấp hơn nhóm so sánh")

            if product.stock >= avg_stock:
                pros.append("Tồn kho ổn định, dễ mua ngay")
            else:
                cons.append("Tồn kho thấp hơn các lựa chọn khác")

            numeric_specs = {k: v for k, v in product.specifications.items() if isinstance(v, (int, float))}
            for key, value in numeric_specs.items():
                peer_values = [
                    p.product.specifications.get(key)
                    for p in ranked_products
                    if p.product.product_id != product.product_id and isinstance(p.product.specifications.get(key), (int, float))
                ]
                if not peer_values:
                    continue
                peer_avg = mean(peer_values)
                if value > peer_avg:
                    pros.append(f"{key} nhỉnh hơn các mẫu còn lại")
                elif value < peer_avg:
                    cons.append(f"{key} thấp hơn một số lựa chọn khác")

            items.append(TradeoffItem(product_name=product.name, pros=pros, cons=cons))

        return TradeoffOutput(items=items)
