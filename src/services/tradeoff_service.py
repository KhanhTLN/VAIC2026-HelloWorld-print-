from __future__ import annotations

from statistics import mean

from src.models.product import RankedProduct
from src.schemas.workflow import TradeoffItem, TradeoffOutput


class TradeoffService:
    def build(self, ranked_products: list[RankedProduct]) -> TradeoffOutput:
        if not ranked_products:
            return TradeoffOutput(items=[], comparison=[])

        prices = [item.product.sale_price for item in ranked_products if item.product.sale_price]
        ratings = [item.product.rating for item in ranked_products]
        sold = [item.product.quantity_sold for item in ranked_products]

        avg_price = mean(prices) if prices else 0
        avg_rating = mean(ratings) if ratings else 0
        avg_sold = mean(sold) if sold else 0

        items: list[TradeoffItem] = []
        comparison: list[dict] = []

        for item in ranked_products:
            product = item.product
            pros: list[str] = []
            cons: list[str] = []

            if avg_price and product.sale_price:
                if product.sale_price <= avg_price:
                    pros.append("Giá cạnh tranh hơn các lựa chọn còn lại")
                else:
                    cons.append("Giá cao hơn mặt bằng các lựa chọn")

            if product.rating >= avg_rating and product.rating > 0:
                pros.append("Đánh giá người dùng tốt")
            elif product.rating < avg_rating:
                cons.append("Điểm đánh giá thấp hơn nhóm so sánh")

            if product.promotion or product.gift_promotion:
                pros.append(f"Có khuyến mãi: {product.promotion or product.gift_promotion}")

            if product.quantity_sold >= avg_sold and product.quantity_sold > 0:
                pros.append("Đang bán chạy")
            elif product.quantity_sold < avg_sold:
                cons.append("Độ phổ biến thấp hơn một số lựa chọn khác")

            if product.outstanding:
                pros.append(product.outstanding[:120])

            # Spec comparison on overlapping keys
            for key, value in product.specifications.items():
                peer_values = []
                for other in ranked_products:
                    if other.product.product_id == product.product_id:
                        continue
                    peer = other.product.specifications.get(key)
                    if isinstance(peer, (int, float)) and isinstance(value, (int, float)):
                        peer_values.append(peer)
                if peer_values and isinstance(value, (int, float)):
                    peer_avg = mean(peer_values)
                    if value > peer_avg:
                        pros.append(f"{key} nhỉnh hơn các mẫu còn lại")
                    elif value < peer_avg:
                        cons.append(f"{key} thấp hơn một số lựa chọn khác")

            if not pros:
                pros.append("Phù hợp với bộ lọc đã chọn")

            items.append(
                TradeoffItem(
                    product_name=product.name,
                    product_id=product.product_id,
                    pros=pros,
                    cons=cons,
                )
            )
            comparison.append(
                {
                    "product": product.name,
                    "product_id": product.product_id,
                    "pros": pros,
                    "cons": cons,
                    "sale_price": product.sale_price,
                    "rating": product.rating,
                    "promotion": product.promotion or None,
                }
            )

        return TradeoffOutput(items=items, comparison=comparison)
