import os
import sys
import json
import psycopg2
from psycopg2.extras import RealDictCursor

# Cấu hình stdout hiển thị tốt Tiếng Việt
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Connection string của Supabase (sử dụng Direct URL để ổn định kết nối đồng bộ)
DB_URL = "postgresql://postgres.bdcsgjmmizlbrgnaztto:PhamTheQuyen2005%40@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"

def get_db_connection():
    return psycopg2.connect(DB_URL)

from decimal import Decimal
import math

def safe_int(val):
    if val is None:
        return 0
    try:
        if isinstance(val, Decimal):
            if val.is_nan():
                return 0
            return int(val)
        val_float = float(val)
        if math.isnan(val_float):
            return 0
        return int(val_float)
    except:
        return 0

def format_price(val):
    price_val = safe_int(val)
    if not price_val:
        return "0đ"
    return f"{price_val:,}".replace(",", ".") + "đ"

def normalize_category(cat_name):
    if not cat_name:
        return "khac"
    cat_lower = cat_name.lower().strip()
    
    # Loại trừ phụ kiện và các nhóm hàng phụ trợ trước
    if any(kw in cat_lower for kw in ["phụ kiện", "phu kien", "ốp", "op", "bao da", "kính cường lực", "dây đeo"]):
        cleaned_slug = cat_lower.replace(" ", "-")
        return cleaned_slug
        
    if cat_lower == "điện thoại" or cat_lower == "dien thoai":
        return "dien-thoai"
    if cat_lower == "máy lạnh" or cat_lower == "may lanh" or cat_lower == "điều hòa" or cat_lower == "dieu hoa":
        return "may-lanh"
    if cat_lower == "tủ lạnh" or cat_lower == "tu lanh":
        return "tu-lanh"
    if cat_lower == "laptop":
        return "laptop"
    if cat_lower == "loa, tai nghe" or cat_lower == "tai nghe" or cat_lower == "headphone":
        return "tai-nghe"
    
    # Fallback clean slug
    cleaned_slug = cat_lower.replace(" ", "-")
    return cleaned_slug

def sync_data():
    print("🔄 Đang kết nối tới Supabase PostgreSQL...")
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT 
                p.product_id, 
                p.name, 
                p.brand, 
                c.category_name, 
                p.sale_price, 
                p.original_price,
                p.promotion, 
                p.outstanding,
                p.spec_product
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
        """
        
        print("📥 Đang tải dữ liệu sản phẩm...")
        cursor.execute(query)
        rows = cursor.fetchall()
        
        cleaned_products = []
        for row in rows:
            price = safe_int(row['sale_price'])
            
            # Chuẩn hóa specifications (JSONB) từ JSON sang chuỗi văn bản để AI đọc
            specs_str = ""
            specs_data = row['spec_product']
            if specs_data:
                if isinstance(specs_data, dict):
                    specs_str = " - ".join([f"{k}: {v}" for k, v in specs_data.items()])
                elif isinstance(specs_data, list):
                    specs_str = " - ".join([str(item) for item in specs_data])
                else:
                    specs_str = str(specs_data)
            
            formatted_price_str = format_price(price)
            description = row['outstanding'] or ""
            normalized_cat = normalize_category(row['category_name'])
            
            # Tạo trường full_text làm giàu ngữ cảnh cho RAG
            full_text = (
                f"Sản phẩm: {row['name']}. "
                f"Thương hiệu: {row['brand'] or 'Khác'}. "
                f"Ngành hàng: {row['category_name'] or 'Khác'}. "
                f"Giá: {formatted_price_str}. "
                f"Thông số: {specs_str}. "
                f"Mô tả: {description}"
            )
            
            cleaned_products.append({
                "id": str(row['product_id']),
                "name": row['name'],
                "brand": (row['brand'] or '').strip().upper(),
                "category": normalized_cat,
                "price": price,
                "specs": specs_str,
                "full_text": full_text,
                "gift_promotion": row['promotion'] or "",
                "stock": 10  # Mặc định gán tồn kho là 10 do schema mới không có cột stock
            })
            
        # Ghi đè vào file local cleaned_catalog.json
        output_dir = 'data/processed'
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'cleaned_catalog.json')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_products, f, indent=4, ensure_ascii=False)
            
        print(f"✅ Đồng bộ thành công {len(cleaned_products)} sản phẩm từ Supabase về {output_path}!")
        
        # Đóng kết nối
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Lỗi trong quá trình đồng bộ: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    sync_data()
