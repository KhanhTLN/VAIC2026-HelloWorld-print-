import pandas as pd
import json
import sys

# Cấu hình stdout hiển thị tốt Tiếng Việt trên terminal Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def clean_and_extract_catalog(file_path):
    # 1. Đọc dữ liệu (Thay 'csv' bằng 'json' nếu dữ liệu dạng JSON)
    df = pd.read_csv(file_path) 
    
    cleaned_products = []
    
    for _, row in df.iterrows():
        # Chuẩn hóa giá tiền về dạng số (int) để dễ so sánh lớn/nhỏ
        try:
            price = int(str(row['price']).replace('.', '').replace('đ', '').strip())
        except:
            price = 0
            
        # Tạo cấu trúc dữ liệu chuẩn cho từng sản phẩm
        product_data = {
            "id": str(row['id']),
            "name": row['name'],
            "brand": row['brand'].strip().upper(),
            "category": row['category'].strip().lower(), # e.g., 'may-lanh', 'dien-thoai'
            "price": price,
            # Lưu các thông số kỹ thuật gốc để AI đọc
            "specs": row['specs'] if 'specs' in df.columns else "", 
            # Đoạn văn bản mô tả đầy đủ phục vụ cho việc Vector Search (RAG)
            "full_text": f"Sản phẩm: {row['name']}. Thương hiệu: {row['brand']}. Ngành hàng: {row['category']}. Giá: {row['price']}. Thông số: {row['specs']}. Mô tả: {row['description']}"
        }
        cleaned_products.append(product_data)
        
    return cleaned_products

# Chạy thử và lưu tạm ra file json sạch
if __name__ == "__main__":
    # Trỏ đúng vào thư mục data/raw và lưu ra data/processed
    cleaned_data = clean_and_extract_catalog('data/raw/catalog.csv') 
    with open('data/processed/cleaned_catalog.json', 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=4)
    print(f"Đã làm sạch và chuẩn hóa {len(cleaned_data)} sản phẩm!")