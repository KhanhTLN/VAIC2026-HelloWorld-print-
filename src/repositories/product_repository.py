from __future__ import annotations

from typing import Any

from src.database.sync_supabase import get_db_connection, safe_int
from src.models.product import ProductRecord

_PRODUCT_SELECT = """
    SELECT
        p.product_id,
        p.product_code,
        p.product_type,
        p.name,
        p.brand,
        p.color,
        p.original_price,
        p.sale_price,
        p.online_sale_only,
        p.rating_vote,
        p.quantity_sold,
        p.accessories,
        p.warranty_policy,
        p.promotion,
        p.outstanding,
        p.spec_product,
        p.url_image,
        p.url,
        p.time_crawler,
        p.category_id,
        c.category_name AS category_name
    FROM products p
    LEFT JOIN categories c ON p.category_id = c.category_id
"""


class ProductRepository:
    def __init__(self, connection_factory=get_db_connection):
        self._connection_factory = connection_factory

    def list_categories(self) -> list[dict[str, Any]]:
        sql = """
            SELECT category_id, category_name
            FROM categories
            WHERE category_name IS NOT NULL
            ORDER BY category_name
        """
        conn = self._connection_factory()
        cur = conn.cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
        finally:
            cur.close()
            conn.close()

        results: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                results.append(
                    {
                        "category_id": row.get("category_id"),
                        "category_name": row.get("category_name"),
                    }
                )
            else:
                results.append({"category_id": row[0], "category_name": row[1]})
        return results

    def get_searchable_specs(self, category: str | None, limit_keys: int = 40) -> list[str]:
        """Discover JSONB keys for a category — never hardcode spec fields."""
        if not category:
            return []
        sql = """
            SELECT DISTINCT jsonb_object_keys(p.spec_product) AS key
            FROM products p
            JOIN categories c ON p.category_id = c.category_id
            WHERE c.category_name ILIKE %s
              AND p.spec_product IS NOT NULL
            ORDER BY key
            LIMIT %s
        """
        conn = self._connection_factory()
        cur = conn.cursor()
        try:
            cur.execute(sql, (f"%{category}%", int(limit_keys)))
            rows = cur.fetchall()
        finally:
            cur.close()
            conn.close()

        keys: list[str] = []
        for row in rows:
            key = row["key"] if isinstance(row, dict) else row[0]
            if key:
                keys.append(str(key))
        return keys

    @staticmethod
    def build_search_query(filters: dict[str, Any], limit: int = 30) -> tuple[str, list[Any]]:
        where_parts: list[str] = ["1=1"]
        params: list[Any] = []

        category = filters.get("category")
        if category:
            where_parts.append("c.category_name ILIKE %s")
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
                where_parts.append(
                    "("
                    "jsonb_extract_path_text(p.spec_product, %s) ILIKE %s"
                    " OR ("
                    "  jsonb_extract_path_text(p.spec_product, %s) ~ '^[0-9]+(\\.[0-9]+)?'"
                    "  AND (regexp_replace(jsonb_extract_path_text(p.spec_product, %s), '[^0-9\\.]', '', 'g'))::numeric >= %s"
                    ")"
                    ")"
                )
                params.extend([key, f"%{val}%", key, key, val])
            else:
                where_parts.append("jsonb_extract_path_text(p.spec_product, %s) ILIKE %s")
                params.extend([key, f"%{val}%"])

        sql = f"""
            {_PRODUCT_SELECT}
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
            {_PRODUCT_SELECT}
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

            def get(k: str, default: Any = None) -> Any:
                mapping = {
                    "product_id": 0,
                    "product_code": 1,
                    "product_type": 2,
                    "name": 3,
                    "brand": 4,
                    "color": 5,
                    "original_price": 6,
                    "sale_price": 7,
                    "online_sale_only": 8,
                    "rating_vote": 9,
                    "quantity_sold": 10,
                    "accessories": 11,
                    "warranty_policy": 12,
                    "promotion": 13,
                    "outstanding": 14,
                    "spec_product": 15,
                    "url_image": 16,
                    "url": 17,
                    "time_crawler": 18,
                    "category_id": 19,
                    "category_name": 20,
                }
                idx = mapping.get(k)
                if idx is None or idx >= len(values):
                    return default
                return values[idx]

        raw_specs = get("spec_product") or {}
        if not isinstance(raw_specs, dict):
            raw_specs = {}

        promotion = str(get("promotion") or "")
        quantity_sold = safe_int(get("quantity_sold"))
        return ProductRecord(
            product_id=str(get("product_id", "")),
            product_code=get("product_code"),
            product_type=get("product_type"),
            name=str(get("name", "")),
            brand=get("brand"),
            category=get("category_name"),
            category_id=safe_int(get("category_id")) or None,
            color=get("color"),
            sale_price=safe_int(get("sale_price")),
            original_price=safe_int(get("original_price")),
            rating=float(get("rating_vote") or 0.0),
            review_count=quantity_sold,
            quantity_sold=quantity_sold,
            stock=quantity_sold,
            online_sale_only=bool(get("online_sale_only") or False),
            promotion=promotion,
            outstanding=str(get("outstanding") or ""),
            accessories=str(get("accessories") or ""),
            warranty_policy=str(get("warranty_policy") or ""),
            gift_promotion=promotion,
            description=str(get("warranty_policy") or ""),
            specifications=raw_specs,
            url_image=get("url_image"),
            url=get("url"),
        )
