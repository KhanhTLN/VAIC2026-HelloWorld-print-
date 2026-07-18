from __future__ import annotations

from typing import Any

from src.database.sync_supabase import get_db_connection, safe_int
from src.models.product import ProductRecord


class ProductRepository:
    def __init__(self, connection_factory=get_db_connection):
        self._connection_factory = connection_factory

    @staticmethod
    def build_search_query(filters: dict[str, Any], limit: int = 30) -> tuple[str, list[Any]]:
        where_parts: list[str] = ["1=1"]
        params: list[Any] = []

        category = filters.get("category")
        if category:
            where_parts.append("c.category_name ILIKE %s")
            params.append(f"%{category}%")

        brand = filters.get("brand")
        if brand:
            where_parts.append("p.brand ILIKE %s")
            params.append(f"%{brand}%")

        min_price = filters.get("min_price")
        if min_price is not None:
            where_parts.append("p.sale_price >= %s")
            params.append(min_price)

        max_price = filters.get("max_price")
        if max_price is not None:
            where_parts.append("p.sale_price <= %s")
            params.append(max_price)

        specs = filters.get("specifications") or {}
        for key, val in specs.items():
            if isinstance(val, dict):
                if "min" in val:
                    where_parts.append("(jsonb_extract_path_text(p.spec_product, %s))::numeric >= %s")
                    params.extend([key, val["min"]])
                if "max" in val:
                    where_parts.append("(jsonb_extract_path_text(p.spec_product, %s))::numeric <= %s")
                    params.extend([key, val["max"]])
            elif isinstance(val, (int, float)):
                where_parts.append("(jsonb_extract_path_text(p.spec_product, %s))::numeric >= %s")
                params.extend([key, val])
            else:
                where_parts.append("jsonb_extract_path_text(p.spec_product, %s) ILIKE %s")
                params.extend([key, f"%{val}%"])

        sql = f"""
            SELECT
                p.id,
                p.name,
                p.brand AS brand_name,
                c.category_name AS category_name,
                p.sale_price,
                p.original_price,
                p.rating_vote AS rating,
                0 AS review_count,
                0 AS stock,
                p.promotion AS gift_promotion,
                p.warranty_policy AS description,
                p.spec_product AS specifications
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY p.sale_price ASC NULLS LAST
            LIMIT {int(limit)}
        """
        return sql, params

    def search_candidates(self, filters: dict[str, Any], limit: int = 30) -> list[ProductRecord]:
        sql, params = self.build_search_query(filters=filters, limit=limit)
        conn = self._connection_factory()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
        finally:
            cur.close()
            conn.close()
        return [self._row_to_product(row) for row in rows]

    def get_products_by_names(self, names: list[str], limit: int = 10) -> list[ProductRecord]:
        if not names:
            return []
        clauses = []
        params: list[Any] = []
        for name in names[:limit]:
            clauses.append("p.name ILIKE %s")
            params.append(f"%{name}%")
        sql = f"""
            SELECT
                p.id,
                p.name,
                p.brand AS brand_name,
                c.category_name AS category_name,
                p.sale_price,
                p.original_price,
                p.rating_vote AS rating,
                0 AS review_count,
                0 AS stock,
                p.promotion AS gift_promotion,
                p.warranty_policy AS description,
                p.spec_product AS specifications
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE {' OR '.join(clauses)}
            LIMIT {int(limit)}
        """
        conn = self._connection_factory()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
        finally:
            cur.close()
            conn.close()
        return [self._row_to_product(row) for row in rows]

    @staticmethod
    def _row_to_product(row: Any) -> ProductRecord:
        if isinstance(row, dict):
            get = row.get
        else:
            values = list(row)
            get = lambda k, default=None: {
                "id": values[0] if len(values) > 0 else default,
                "name": values[1] if len(values) > 1 else default,
                "brand_name": values[2] if len(values) > 2 else default,
                "category_name": values[3] if len(values) > 3 else default,
                "sale_price": values[4] if len(values) > 4 else default,
                "original_price": values[5] if len(values) > 5 else default,
                "rating": values[6] if len(values) > 6 else default,
                "review_count": values[7] if len(values) > 7 else default,
                "stock": values[8] if len(values) > 8 else default,
                "gift_promotion": values[9] if len(values) > 9 else default,
                "description": values[10] if len(values) > 10 else default,
                "specifications": values[11] if len(values) > 11 else default,
            }.get(k, default)

        raw_specs = get("specifications") or {}
        if not isinstance(raw_specs, dict):
            raw_specs = {}
        return ProductRecord(
            product_id=str(get("id", "")),
            name=str(get("name", "")),
            brand=get("brand_name"),
            category=get("category_name"),
            sale_price=safe_int(get("sale_price")),
            original_price=safe_int(get("original_price")),
            rating=float(get("rating") or 0.0),
            review_count=int(get("review_count") or 0),
            stock=int(get("stock") or 0),
            gift_promotion=str(get("gift_promotion") or ""),
            description=str(get("description") or ""),
            specifications=raw_specs,
        )
