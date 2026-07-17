import pandas as pd
from sqlalchemy import create_engine, text
import json

# ==========================
# CONFIG
# ==========================

CSV_FILE = r"D:\Download\Spec_cate_gia.xlsx - Máy nước nóng.csv"

DATABASE_URL = "postgresql+psycopg2://postgres.bdcsgjmmizlbrgnaztto:PhamTheQuyen2005%40@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

# Connect to Postgres via the shared session-mode pooler (used for migrations)

engine = create_engine(DATABASE_URL)

# Những cột lưu riêng
METADATA_FIELDS = {
    "model_code",
    "sku",
    "productidweb",
    "category_code",
    "brand_id",
    "brand",
    "giá gốc",
    "giá khuyến mãi",
    "khuyến mãi quà",
}

# ==========================
# READ CSV
# ==========================

df = pd.read_csv(CSV_FILE)

with engine.begin() as conn:

    for _, row in df.iterrows():

        # Metadata
        model_code = row.get("model_code")
        sku = row.get("sku")
        product_id_web = row.get("productidweb")
        category_code = row.get("category_code")
        brand_id = row.get("brand_id")
        brand = row.get("brand")

        original_price = row.get("giá gốc")
        sale_price = row.get("giá khuyến mãi")
        gift = row.get("khuyến mãi quà")

        # Lấy tên sản phẩm nếu có
        name = row.get("name") or row.get("Tên sản phẩm") or sku

        # Build JSONB
        specifications = {}

        for column in df.columns:

            if column in METADATA_FIELDS:
                continue

            value = row[column]

            if pd.isna(value):
                continue

            if isinstance(value, str):
                value = value.strip()

                if value == "":
                    continue

            specifications[column] = value

        conn.execute(
            text("""
                INSERT INTO products (
                    model_code,
                    sku,
                    product_id_web,
                    name,
                    category_id,
                    brand_id,
                    description,
                    original_price,
                    sale_price,
                    gift_promotion,
                    specifications
                )
                VALUES (
                    :model_code,
                    :sku,
                    :product_id_web,
                    :name,
                    :category_id,
                    :brand_id,
                    '',
                    :original_price,
                    :sale_price,
                    :gift_promotion,
                    CAST(:specifications AS JSONB)
                )
            """),
            {
                "model_code": model_code,
                "sku": sku,
                "product_id_web": product_id_web,
                "name": name,
                "category_id": category_code,
                "brand_id": brand_id,
                "original_price": original_price,
                "sale_price": sale_price,
                "gift_promotion": gift,
                "specifications": json.dumps(
                    specifications,
                    ensure_ascii=False
                )
            }
        )

print("Import completed.")