from fastapi import FastAPI, HTTPException
import json

app = FastAPI(title="Điện Máy Xanh Mock API - VIC 2026")

# Tải dữ liệu sản phẩm để làm database giả lập
try:
    with open('data/processed/cleaned_catalog.json', 'r', encoding='utf-8') as f:
        products_db = {p['id']: p for p in json.load(f)}
except FileNotFoundError:
    products_db = {}

@app.get("/api/stock/{product_id}")
def get_stock(product_id: str, province: str = "Đà Nẵng"):
    """API kiểm tra tồn kho theo khu vực"""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    # Giả lập logic tồn kho: ID chẵn thì còn hàng, lẻ thì hết hàng ở Đà Nẵng
    is_available = int(product_id[-1]) % 2 == 0 if product_id[-1].isdigit() else True
    
    return {
        "product_id": product_id,
        "product_name": products_db[product_id]['name'],
        "province": province,
        "status": "Còn hàng" if is_available else "Hết hàng tại khu vực này",
        "stock_count": 15 if is_available else 0
    }

@app.get("/api/promotion/{product_id}")
def get_promotion(product_id: str):
    """API lấy chương trình khuyến mãi theo thời gian thực"""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    # Giả lập chương trình khuyến mãi dựa trên giá
    price = products_db[product_id]['price']
    if price > 15000000:
        return {
            "product_id": product_id,
            "discount_gift": "Tặng Phiếu mua hàng 500.000đ + Miễn phí lắp đặt tận nhà",
            "installment": "Hỗ trợ trả góp 0% qua thẻ tín dụng"
        }
    else:
        return {
            "product_id": product_id,
            "discount_gift": "Miễn phí giao hàng trong vòng 2 tiếng",
            "installment": "Không áp dụng trả góp 0%"
        }

# Lệnh chạy server mock: uvicorn mock_api:app --reload --port 8000