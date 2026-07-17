from decimal import Decimal
from typing import Any

from schemas.product import ProductRead
from schemas.search import SearchRequest


def _price(product: ProductRead) -> Decimal | None:
    if product.sale_price is not None:
        return product.sale_price
    return product.original_price


def rank_products(
    products: list[ProductRead],
    request: SearchRequest,
    *,
    top_n: int = 3,
) -> list[tuple[ProductRead, float]]:
    """
    MVP ranking — pure backend, no LLM.

    Score weights:
    - budget fit (how close to max_price / within budget)
    - rating
    - review_count
    """
    if not products:
        return []

    scored: list[tuple[ProductRead, float]] = []
    for product in products:
        score = 0.0
        price = _price(product)

        if request.max_price is not None and price is not None and request.max_price > 0:
            if price <= request.max_price:
                # Prefer products closer to budget (better value perception).
                ratio = float(price / request.max_price)
                score += 40.0 * (0.5 + 0.5 * ratio)
            else:
                score -= 20.0
        elif price is not None:
            score += 10.0

        if product.rating is not None:
            score += float(product.rating) * 8.0

        if product.review_count:
            score += min(float(product.review_count), 500.0) / 50.0

        scored.append((product, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_n]


def build_tradeoffs(
    ranked: list[tuple[ProductRead, float]],
) -> list[dict[str, Any]]:
    """Compare top products on price / rating / stock — no LLM."""
    if not ranked:
        return []

    prices = [(_price(p), p) for p, _ in ranked if _price(p) is not None]
    ratings = [(p.rating, p) for p, _ in ranked if p.rating is not None]

    cheapest_id = min(prices, key=lambda x: x[0])[1].id if prices else None
    best_rated_id = max(ratings, key=lambda x: x[0])[1].id if ratings else None

    results: list[dict[str, Any]] = []
    for product, score in ranked:
        strengths: list[str] = []
        weaknesses: list[str] = []

        if product.id == cheapest_id:
            strengths.append("Giá tốt nhất trong các lựa chọn")
        if (
            product.id == best_rated_id
            and product.rating is not None
            and float(product.rating) > 0
        ):
            strengths.append(f"Đánh giá cao nhất ({product.rating})")
        if product.stock and product.stock > 0:
            strengths.append("Còn hàng")
        elif product.stock == 0:
            weaknesses.append("Hết hàng")

        if not strengths:
            strengths.append("Phù hợp với bộ lọc đã chọn")

        price = _price(product)
        if (
            price is not None
            and cheapest_id is not None
            and product.id != cheapest_id
            and len(ranked) > 1
        ):
            weaknesses.append("Giá cao hơn lựa chọn rẻ nhất")

        results.append(
            {
                "product_id": product.id,
                "score": round(score, 2),
                "strength": strengths,
                "weakness": weaknesses,
            }
        )
    return results


def generate_answer(
    request: SearchRequest,
    ranked: list[tuple[ProductRead, float]],
    tradeoffs: list[dict[str, Any]],
    *,
    total: int,
    suggestions: list[ProductRead] | None = None,
) -> str:
    """MVP response generator — template tiếng Việt, không gọi LLM."""
    if not ranked:
        lines = [
            "Không tìm thấy sản phẩm khớp đúng nhu cầu của bạn.",
        ]
        if suggestions:
            lines.append("Gợi ý một số sản phẩm bán chạy:")
            for item in suggestions[:3]:
                price = _price(item)
                price_text = f"{price:,.0f}đ" if price is not None else "liên hệ"
                lines.append(f"- {item.name} ({price_text})")
        return "\n".join(lines)

    top, top_score = ranked[0]
    top_price = _price(top)
    price_text = f"{top_price:,.0f}đ" if top_price is not None else "liên hệ"

    need_bits: list[str] = []
    if request.category:
        need_bits.append(f"ngành hàng {request.category}")
    if request.brand:
        need_bits.append(f"thương hiệu {request.brand}")
    if request.max_price is not None:
        need_bits.append(f"ngân sách tối đa {request.max_price:,.0f}đ")
    need_text = ", ".join(need_bits) if need_bits else "tiêu chí đã chọn"

    lines = [
        f"Dựa trên {need_text}, hệ thống tìm thấy {total} sản phẩm phù hợp.",
        f"Gợi ý hàng đầu: {top.name} — khoảng {price_text} (điểm {top_score:.1f}).",
    ]

    if tradeoffs:
        top_trade = tradeoffs[0]
        if top_trade.get("strength"):
            lines.append("Điểm mạnh: " + "; ".join(top_trade["strength"]) + ".")
        if top_trade.get("weakness"):
            lines.append("Lưu ý: " + "; ".join(top_trade["weakness"]) + ".")

    if len(ranked) > 1:
        lines.append("Các lựa chọn khác:")
        for product, score in ranked[1:]:
            p = _price(product)
            p_text = f"{p:,.0f}đ" if p is not None else "liên hệ"
            lines.append(f"- {product.name} ({p_text}, điểm {score:.1f})")

    return "\n".join(lines)
