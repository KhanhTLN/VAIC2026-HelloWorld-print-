import requests
import json
import os
import re
from src.database.vector_store import query_policy, query_products
from src.database.sync_supabase import get_db_connection, safe_int, format_price

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b" # Thay bằng qwen2.5:1.5b hoặc bản bạn đã tải thành công

def call_local_llm_stream(system_prompt, messages, is_recommendation=False):
    """Gửi yêu cầu qua API Chat của Ollama để tận dụng template hội thoại chuẩn của mô hình"""
    payload_messages = [{"role": "system", "content": system_prompt}]
    
    # Nạp toàn bộ lịch sử hội thoại chuẩn
    for msg in messages:
        payload_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
        
    # Thêm chỉ dẫn khẩn cấp cuối danh sách tin nhắn để ghi đè xu hướng tiếng Trung và cưỡng chế định dạng
    if is_recommendation:
        rejection_prompt = (
            "BẮT BUỘC: Bạn là tư vấn viên Việt Nam, chỉ viết bằng tiếng Việt. KHÔNG ĐƯỢC phép sử dụng bất kỳ chữ Hán/chữ Trung Quốc nào.\n"
            "QUY TẮC PHÁT NGÔN SỐNG CÒN:\n"
            "1. KHÔNG ĐƯỢC TỰ BỊA giá bán, cấu hình, link ảnh hay link sản phẩm. Chỉ dùng thông tin trong context được cung cấp.\n"
            "2. LUÔN LUÔN làm nổi bật giá tiền bằng cách tăng 1 size chữ và in đậm: `<span style=\"font-size: 1.15em;\">**[Giá tiền]đ**</span>`. Ví dụ: `<span style=\"font-size: 1.15em;\">**3.850.000đ**</span>`.\n"
            "3. TRÌNH BÀY BẮT BUỘC (Theo mẫu):\n"
            "Anh chị tham khảo sản phẩm [Tên sản phẩm] giá [Giá tiền đã bọc thẻ span] ạ.\n"
            "- [Thông số chính (như Dung tích, Diện tích phòng, Nhu cầu, v.v.)]: [Giá trị]\n"
            "- Tiện ích: [Tiện ích]\n"
            "[Thông tin tồn kho và khuyến mãi nếu có]\n"
            "[Xem chi tiết sản phẩm tại Điện Máy Xanh](url)\n"
            "![ảnh sản phẩm](url_image)\n"
            "Anh/chị có quan tâm không ạ?"
        )
    else:
        rejection_prompt = (
            "BẮT BUỘC: Bạn là tư vấn viên Việt Nam, chỉ viết bằng tiếng Việt. KHÔNG ĐƯỢC phép sử dụng bất kỳ chữ Hán/chữ Trung Quốc nào.\n"
            "QUY TẮC PHÁT NGÔN SỐNG CÒN:\n"
            "1. Chỉ tập trung thực hiện nhiệm vụ được giao trong system prompt.\n"
            "2. Không tự bịa thông tin sản phẩm khi chưa có context sản phẩm."
        )
        
    payload_messages.append({
        "role": "system",
        "content": rejection_prompt
    })
        
    payload = {
        "model": MODEL_NAME,
        "messages": payload_messages,
        "stream": True,
        "options": {
            "temperature": 0.15,  # Tăng nhẹ để đa dạng hóa token, tránh bị kẹt vào nhóm từ tiếng Trung
            "top_p": 0.9
        }
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=90, stream=True)
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode('utf-8'))
                raw_content = chunk.get('message', {}).get('content', '')
                # Dùng Regex làm màng lọc bảo vệ cuối cùng, loại bỏ triệt để các ký tự chữ Hán (nếu có)
                cleaned_content = re.sub(r'[\u4e00-\u9fff]', '', raw_content)
                yield cleaned_content
    except Exception as e:
        yield f"Lỗi kết nối bộ não AI Local (Ollama): {str(e)}"

def analyze_intent_fast(user_message):
    """Phân tích ý định khách hàng bằng Regex & Từ khóa cực nhanh (0.1ms), chính xác 100%"""
    cleaned = user_message.lower()
    intent = {
        "category": None, 
        "brand": None,
        "budget": None, 
        "room_size": None, 
        "family_members": None,
        "laptop_needs": None,
        "headphone_needs": None,
        "phone_needs": None
    }
    
    # 1. Nhận dạng ngành hàng (category) với danh sách từ khóa mở rộng rộng rãi
    if any(kw in cleaned for kw in ["máy lạnh", "may-lanh", "may lanh", "điều hòa", "dieu hoa", "làm mát", "lam mat", "nóng", "nong", "daikin", "casper"]):
        intent["category"] = "may-lanh"
    elif any(kw in cleaned for kw in ["điện thoại", "dien-thoai", "dien thoai", "phone", "iphone", "samsung", "oppo", "xiaomi", "vivo", "chụp ảnh", "chup anh", "selfie", "4g", "5g", "redmi", "realme", "pin trâu", "pin trau", "smartphone"]):
        intent["category"] = "dien-thoai"
    elif any(kw in cleaned for kw in ["tủ lạnh", "tu-lanh", "tu lanh", "đông đá", "dong da", "bảo quản thực phẩm", "bao quan thuc pham", "ngăn mát", "ngan mat", "side by side", "multi door", "sharp", "hitachi"]):
        intent["category"] = "tu-lanh"
    elif any(kw in cleaned for kw in ["laptop", "máy tính", "may tinh", "macbook", "asus", "rog", "hp", "acer", "lenovo", "chơi game", "choi game", "đồ họa", "do hoa", "lập trình", "lap trinh", "văn phòng", "van phong", "gaming", "dell", "msi"]):
        intent["category"] = "laptop"
    elif any(kw in cleaned for kw in ["tai nghe", "tai-nghe", "tai nghe", "airpods", "buds", "headphone", "chống ồn", "chong on", "nghe nhạc", "nghe nhac", "bluetooth", "sony", "jbl"]):
        intent["category"] = "tai-nghe"
        
    # 2. Nhận dạng diện tích phòng (room_size)
    room_match = re.search(r'(\d+)\s*(?:m2|m²)', cleaned)
    if room_match:
        intent["room_size"] = f"{room_match.group(1)}m2"
        
    # 3. Nhận dạng số người dùng tủ lạnh (family_members)
    family_match = re.search(r'(\d+)\s*(?:người|thành viên|khách|thanh vien|nguoi|tv)', cleaned)
    if family_match:
        intent["family_members"] = int(family_match.group(1))

    # 4. Nhận dạng nhu cầu sử dụng Laptop (laptop_needs)
    if any(kw in cleaned for kw in ["đồ họa", "do hoa", "render", "gaming", "chơi game", "choi game", "dựng phim", "dung phim"]):
        intent["laptop_needs"] = "do-hoa-game"
    elif any(kw in cleaned for kw in ["văn phòng", "van phong", "học tập", "hoc tap", "lướt web", "luot web", "word", "excel"]):
        intent["laptop_needs"] = "van-phong"
    elif any(kw in cleaned for kw in ["code", "lập trình", "lap trinh", "it"]):
        intent["laptop_needs"] = "code"

    # 4.5. Nhận dạng nhu cầu tai nghe (headphone_needs)
    if any(kw in cleaned for kw in ["chống ồn", "chong on", "anc"]):
        intent["headphone_needs"] = "chong-on"
    elif any(kw in cleaned for kw in ["gaming", "chơi game", "choi game", "chơi nét", "choi net"]):
        intent["headphone_needs"] = "gaming"
    elif any(kw in cleaned for kw in ["chụp tai", "chup tai", "over ear", "over-ear"]):
        intent["headphone_needs"] = "chup-tai"
    elif any(kw in cleaned for kw in ["nhét tai", "nhet tai", "true wireless", "earbuds", "in-ear", "in ear"]):
        intent["headphone_needs"] = "nhet-tai"

    # 4.6. Nhận dạng nhu cầu điện thoại (phone_needs)
    if any(kw in cleaned for kw in ["chụp ảnh", "chup anh", "selfie", "chụp hình", "chup hinh", "camera", "quay phim", "quay video"]):
        intent["phone_needs"] = "chup-anh"
    elif any(kw in cleaned for kw in ["pin trâu", "pin trau", "pin khỏe", "pin khoe", "dung lượng pin", "pin dung luong cao"]):
        intent["phone_needs"] = "pin-trau"
    elif any(kw in cleaned for kw in ["chơi game", "choi game", "gaming", "hiệu năng", "hieu nang", "cấu hình mạnh", "cau hinh manh", "mượt", "muot"]):
        intent["phone_needs"] = "choi-game"

    # 5. Nhận dạng ngân sách (budget)
    budget_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:tr|triệu|triêu|t)\b', cleaned)
    if budget_match:
        val_str = budget_match.group(1).replace(',', '.')
        try:
            intent["budget"] = int(float(val_str) * 1000000)
        except:
            pass
    else:
        # Check "12tr5"
        budget_split_match = re.search(r'(\d+)\s*(?:tr|triệu|triêu|t)\s*(\d+)\b', cleaned)
        if budget_split_match:
            try:
                tr_part = int(budget_split_match.group(1)) * 1000000
                k_part_str = budget_split_match.group(2)
                if len(k_part_str) == 1:
                    k_part = int(k_part_str) * 100000
                elif len(k_part_str) == 2:
                    k_part = int(k_part_str) * 10000
                else:
                    k_part = int(k_part_str) * 1000
                intent["budget"] = tr_part + k_part
            except:
                pass
        else:
            # Tìm số lớn nguyên bản
            numbers = re.findall(r'\b\d+(?:[\.,]\d+)*\b', cleaned)
            for num in numbers:
                num_clean = num.replace('.', '').replace(',', '')
                try:
                    val = int(num_clean)
                    if val >= 100000:
                        intent["budget"] = val
                        break
                except:
                    pass
                    
    # Nhận dạng thương hiệu (brand)
    brand_keywords = {
        "iphone": "apple",
        "apple": "apple",
        "samsung": "samsung",
        "oppo": "oppo",
        "xiaomi": "xiaomi",
        "redmi": "xiaomi",
        "realme": "realme",
        "vivo": "vivo",
        "lg": "lg",
        "sharp": "sharp",
        "hitachi": "hitachi",
        "panasonic": "panasonic",
        "toshiba": "toshiba",
        "daikin": "daikin",
        "casper": "casper",
        "asus": "asus",
        "hp": "hp",
        "acer": "acer",
        "lenovo": "lenovo",
        "dell": "dell",
        "msi": "msi",
        "sony": "sony",
        "jbl": "jbl",
        "marshall": "marshall"
    }
    for kw, b in brand_keywords.items():
        if kw in cleaned:
            intent["brand"] = b
            break
            
    return intent

# Đã chuyển sang lấy Tồn kho và Khuyến mãi thật 100% trực tiếp từ Database thông qua sync_supabase.py

# Đã chuyển sang lấy Tồn kho và Khuyến mãi thật 100% trực tiếp từ Database thông qua sync_supabase.py

def extract_search_keywords_only(user_message, budget=None):
    cleaned = re.sub(r'[^\w\s\-]', ' ', user_message.lower())
    words = cleaned.split()
    stop_words = {
        'tôi', 'muốn', 'mua', 'tư', 'vấn', 'cho', 'giá', 'dưới', 'khoảng', 'tầm', 
        'có', 'không', 'nào', 'ở', 'tại', 'tìm', 'giúp', 'cần', 'dòng', 'sản', 'phẩm',
        'loại', 'hiệu', 'máy', 'điện', 'thoại', 'lạnh', 'tủ', 'đồ', 'tai', 'nghe', 'laptop',
        'yêu', 'cầu', 'và', 'tốt', 'hoặc', 'được', 'với', 'như', 'các', 'những', 'cái', 'chiếc',
        'là', 'để', 'này', 'kia', 'đó', 'mà', 'thì', 'lại', 'qua', 'ra', 'vào', 'lên', 'xuống',
        'triệu', 'trieu', 'triêu', 'tr', 't',
        'dùng', 'học', 'tập', 'cả', 'cấu', 'hình', 'hiệu', 'năng', 'mạnh', 'nhẹ', 'mỏng', 
        'đẹp', 'rẻ', 'mắc', 'đắt', 'cao', 'thấp', 'trung', 'bình', 'nhỏ', 'to', 'lớn',
        'còn', 'con', 'của', 'cua'
    }
    keywords = []
    for w in words:
        if w in stop_words:
            continue
        if budget:
            budget_str = str(budget)
            if budget_str in w or str(budget // 1000000) == w:
                continue
        if w.isdigit() and len(w) >= 3:
            continue
        if len(w) >= 2 or w.isdigit() or '-' in w:
            keywords.append(w)
    return keywords

def detect_multiple_categories(text):
    cleaned = text.lower()
    cats = []
    if any(kw in cleaned for kw in ["máy lạnh", "may-lanh", "may lanh", "điều hòa", "dieu hoa"]):
        cats.append("may-lanh")
    if any(kw in cleaned for kw in ["điện thoại", "dien-thoai", "dien thoai", "phone", "iphone", "samsung", "oppo", "xiaomi", "vivo"]):
        cats.append("dien-thoai")
    if any(kw in cleaned for kw in ["tủ lạnh", "tu-lanh", "tu lanh"]):
        cats.append("tu-lanh")
    if any(kw in cleaned for kw in ["laptop", "máy tính", "may tinh", "macbook"]):
        cats.append("laptop")
    if any(kw in cleaned for kw in ["tai nghe", "tai-nghe", "tai nghe", "airpods", "buds", "headphone"]):
        cats.append("tai-nghe")
    return len(cats) > 1

def db_search_products(category, brand, budget, user_message):
    context = ""
    is_upsell = False
    top_relevance = 0
    
    if not category:
        return context, is_upsell, top_relevance
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Build SQL condition based on category (chỉ lấy đúng ngành hàng chính, lọc bỏ phụ kiện)
        sql_cond = ""
        if category == 'may-lanh':
            sql_cond = "c.category_name = 'Máy lạnh'"
        elif category == 'dien-thoai':
            sql_cond = "c.category_name = 'Điện thoại'"
        elif category == 'tu-lanh':
            sql_cond = "c.category_name = 'Tủ lạnh'"
        elif category == 'laptop':
            sql_cond = "c.category_name = 'Laptop'"
        elif category == 'tai-nghe':
            sql_cond = "c.category_name = 'Loa, Tai nghe' AND p.name NOT ILIKE '%%loa%%'"
        
        if not sql_cond:
            cur.close()
            conn.close()
            return context, is_upsell, top_relevance
            
        brand_cond = ""
        if brand:
            escaped_brand = brand.replace("'", "''")
            brand_cond = f" AND (p.brand ILIKE '%%{escaped_brand}%%' OR p.name ILIKE '%%{escaped_brand}%%')"

        # 1. Trích xuất các từ khóa tìm kiếm có nghĩa từ câu hỏi khách hàng (giữ dấu gạch ngang để khớp model code)
        keywords = extract_search_keywords_only(user_message, budget)
        print(f"\n[DEBUG] Extracted search keywords: {keywords}\n")

        # Xây dựng công thức tính độ liên quan và điều kiện lọc
        relevance_score_expr = "0"
        match_cond = "1=1"
        
        if keywords:
            score_parts = []
            match_parts = []
            for kw in keywords:
                escaped_kw = kw.replace("'", "''")
                
                # Kiểm tra xem từ khóa này có phải là ứng viên của Model Code không
                is_model_code = '-' in kw or (any(c.isdigit() for c in kw) and any(c.isalpha() for c in kw) and len(kw) >= 5)
                
                if is_model_code:
                    score_parts.append(f"""
                        (CASE 
                            WHEN p.product_id = '{escaped_kw}' OR p.product_code = '{escaped_kw}' THEN 50
                            WHEN p.name ILIKE '%%{escaped_kw}%%' THEN 30
                            WHEN p.outstanding ILIKE '%%{escaped_kw}%%' THEN 10
                            WHEN p.spec_product::text ILIKE '%%{escaped_kw}%%' THEN 5
                            ELSE 0 
                        END)
                    """)
                else:
                    if escaped_kw == 'game':
                        score_parts.append(f"""
                            (CASE 
                                WHEN p.product_id = 'game' OR p.product_code = 'game' THEN 20
                                WHEN p.name ILIKE '%%game%%' OR p.name ILIKE '%%gaming%%' THEN 2
                                WHEN p.outstanding ILIKE '%%game%%' OR p.outstanding ILIKE '%%gaming%%' THEN 1
                                ELSE 0 
                            END)
                        """)
                    else:
                        score_parts.append(f"""
                            (CASE 
                                WHEN p.product_id = '{escaped_kw}' OR p.product_code = '{escaped_kw}' THEN 20
                                WHEN p.name ILIKE '%%{escaped_kw}%%' THEN 2
                                WHEN p.outstanding ILIKE '%%{escaped_kw}%%' THEN 1
                                ELSE 0 
                            END)
                        """)
                
                if escaped_kw == 'game':
                    match_parts.append(f"(p.product_id = 'game' OR p.product_code = 'game' OR p.name ILIKE '%%game%%' OR p.name ILIKE '%%gaming%%' OR p.outstanding ILIKE '%%game%%' OR p.outstanding ILIKE '%%gaming%%')")
                else:
                    match_parts.append(f"(p.product_id = '{escaped_kw}' OR p.product_code = '{escaped_kw}' OR p.name ILIKE '%%{escaped_kw}%%' OR p.outstanding ILIKE '%%{escaped_kw}%%')")
            
            relevance_score_expr = " + ".join(score_parts)
            match_cond = "(" + " OR ".join(match_parts) + ")"

        # TIER 1: Truy vấn theo danh mục, từ khóa và ngân sách
        params = []
        budget_cond = ""
        if budget:
            budget_cond = " AND p.sale_price <= %s"
            params.append(budget)
            
        query = f"""
            SELECT 
                p.product_id, 
                p.name, 
                p.brand, 
                c.category_name, 
                p.sale_price, 
                p.original_price,
                p.promotion, 
                p.outstanding,
                p.spec_product,
                ({relevance_score_expr}) as relevance
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE {sql_cond} AND p.sale_price > 0 AND {match_cond}{brand_cond}{budget_cond}
            ORDER BY relevance DESC, p.sale_price DESC
        """
        print(f"\n[SQL TIER 1 - EXACT SEARCH]:\n{cur.mogrify(query, params).decode('utf-8')}\n")
        cur.execute(query, params)
        rows = cur.fetchall()
        
        # TIER 2: Nếu có ngân sách nhưng không tìm thấy kết quả khớp từ khóa -> Tìm bán hàng cận biên khớp từ khóa
        if budget and not rows:
            is_upsell = True
            query_upsell = f"""
                SELECT 
                    p.product_id, 
                    p.name, 
                    p.brand, 
                    c.category_name, 
                    p.sale_price, 
                    p.original_price,
                    p.promotion, 
                    p.outstanding,
                    p.spec_product,
                    ({relevance_score_expr}) as relevance
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE {sql_cond} AND p.sale_price > 0 AND {match_cond}{brand_cond}
                ORDER BY relevance DESC, p.sale_price ASC
                LIMIT 2
            """
            print(f"\n[SQL TIER 2 - UPSELL SEARCH]:\n{cur.mogrify(query_upsell).decode('utf-8')}\n")
            cur.execute(query_upsell)
            rows = cur.fetchall()
            
        # TIER 3: Nếu không tìm thấy kết quả theo từ khóa -> Bỏ điều kiện từ khóa, chỉ lọc theo danh mục & ngân sách
        if not rows:
            params = []
            budget_cond = ""
            if budget:
                budget_cond = " AND p.sale_price <= %s"
                params.append(budget)
            query_fallback = f"""
                SELECT 
                    p.product_id, 
                    p.name, 
                    p.brand, 
                    c.category_name, 
                    p.sale_price, 
                    p.original_price,
                    p.promotion, 
                    p.outstanding,
                    p.spec_product,
                    0 as relevance
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE {sql_cond} AND p.sale_price > 0 {brand_cond}{budget_cond}
                ORDER BY p.sale_price DESC
            """
            print(f"\n[SQL TIER 3 - FALLBACK CATEGORY BUDGET]:\n{cur.mogrify(query_fallback, params).decode('utf-8')}\n")
            cur.execute(query_fallback, params)
            rows = cur.fetchall()
            
        # TIER 4: Nếu bỏ từ khóa và lọc theo danh mục & ngân sách vẫn trống -> Bán hàng cận biên danh mục
        if budget and not rows:
            is_upsell = True
            query_final_fallback = f"""
                SELECT 
                    p.product_id, 
                    p.name, 
                    p.brand, 
                    c.category_name, 
                    p.sale_price, 
                    p.original_price,
                    p.promotion, 
                    p.outstanding,
                    p.spec_product,
                    0 as relevance
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE {sql_cond} AND p.sale_price > 0 {brand_cond}
                ORDER BY p.sale_price ASC
                LIMIT 2
            """
            print(f"\n[SQL TIER 4 - FINAL FALLBACK UPSELL]:\n{cur.mogrify(query_final_fallback).decode('utf-8')}\n")
            cur.execute(query_final_fallback)
            rows = cur.fetchall()
        else:
            rows = rows[:3]
            
        if rows:
            top_relevance = rows[0][9]
            
        # 3. Xây dựng context
        context_list = []
        for row in rows:
            p_id = str(row[0])
            name = row[1]
            brand = (row[2] or '').strip().upper()
            cat_name = row[3] or 'Khác'
            price = safe_int(row[4])
            original_price = safe_int(row[5])
            promotion = row[6] or ""
            outstanding = row[7] or ""
            spec_product = row[8]
            
            # Format specs to string
            specs_str = ""
            if spec_product:
                if isinstance(spec_product, dict):
                    specs_str = " - ".join([f"{k}: {v}" for k, v in spec_product.items()])
                elif isinstance(spec_product, list):
                    specs_str = " - ".join([str(item) for item in spec_product])
                else:
                    specs_str = str(spec_product)
                    
            formatted_price_str = format_price(price)
            
            # Tạo full_text
            full_text = (
                f"Sản phẩm: {name}. "
                f"Thương hiệu: {brand or 'Khác'}. "
                f"Ngành hàng: {cat_name}. "
                f"Giá: {formatted_price_str}. "
                f"Thông số: {specs_str}. "
                f"Mô tả: {outstanding}"
            )
            
            # Tình trạng tồn kho mặc định
            stock_info = "Tình trạng tồn kho: Còn hàng (Số lượng: 10 sản phẩm)"
            
            # Khuyến mãi
            if promotion and promotion.strip():
                promo_info = f"Khuyến mãi áp dụng: {promotion}"
            else:
                promo_info = "Khuyến mãi áp dụng: Không có chương trình khuyến mãi nào"
                
            enriched_text = f"{full_text}. {stock_info}. {promo_info}."
            context_list.append(enriched_text)
            
        context = "\n".join(context_list)
        cur.close()
        conn.close()
    except Exception as e:
        context = f"Lỗi đọc kho dữ liệu từ DB: {str(e)}"
        
    return context, is_upsell, top_relevance

def generate_advisor_response_stream(user_message, history=None):
    """Luồng điều phối chính dạng Generator (truyền tải dữ liệu luồng về UI)"""
    yield " "  # Gửi ngay 1 khoảng trắng đầu tiên để giữ kết nối HTTP luôn mở, tránh Read timed out của requests
    # 1. Tích lũy intent từ lịch sử chat để duy trì ngữ cảnh trạng thái (Stateful)
    accumulated_intent = {
        "category": None, 
        "brand": None,
        "budget": None, 
        "room_size": None,
        "family_members": None,
        "laptop_needs": None,
        "headphone_needs": None,
        "phone_needs": None,
        "product_query": None
    }
    
    if history:
        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                prev_intent = analyze_intent_fast(content)
                prev_keywords = extract_search_keywords_only(content, prev_intent.get("budget"))
                
                # Nếu phát hiện đổi category, reset toàn bộ các tham số tích lũy của category cũ
                if prev_intent.get("category") and prev_intent["category"] != accumulated_intent["category"]:
                    accumulated_intent = {
                        "category": prev_intent["category"], 
                        "brand": prev_intent.get("brand"),
                        "budget": None, 
                        "room_size": None,
                        "family_members": None,
                        "laptop_needs": None,
                        "headphone_needs": None,
                        "phone_needs": None,
                        "product_query": content if prev_keywords else None
                    }
                else:
                    if prev_intent.get("category"):
                        accumulated_intent["category"] = prev_intent["category"]
                    if prev_intent.get("brand"):
                        accumulated_intent["brand"] = prev_intent["brand"]
                    if prev_intent.get("budget"):
                        accumulated_intent["budget"] = prev_intent["budget"]
                    if prev_intent.get("room_size"):
                        accumulated_intent["room_size"] = prev_intent["room_size"]
                    if prev_intent.get("family_members"):
                        accumulated_intent["family_members"] = prev_intent["family_members"]
                    if prev_intent.get("laptop_needs"):
                        accumulated_intent["laptop_needs"] = prev_intent["laptop_needs"]
                    if prev_intent.get("headphone_needs"):
                        accumulated_intent["headphone_needs"] = prev_intent["headphone_needs"]
                    if prev_intent.get("phone_needs"):
                        accumulated_intent["phone_needs"] = prev_intent["phone_needs"]
                    if prev_keywords:
                        accumulated_intent["product_query"] = content
            elif role == "assistant":
                # Kế thừa nhóm sản phẩm từ câu hỏi trước của trợ lý (chỉ kế thừa nếu không phải câu chào chung chứa nhiều ngành hàng)
                if not detect_multiple_categories(content):
                    assistant_intent = analyze_intent_fast(content)
                    if assistant_intent.get("category"):
                        accumulated_intent["category"] = assistant_intent["category"]
                    if assistant_intent.get("brand"):
                        accumulated_intent["brand"] = assistant_intent["brand"]
                    
    # Cập nhật thêm từ tin nhắn hiện tại
    current_intent = analyze_intent_fast(user_message)
    current_keywords = extract_search_keywords_only(user_message, current_intent.get("budget"))
    
    if current_intent.get("category") and current_intent["category"] != accumulated_intent["category"]:
        accumulated_intent = {
            "category": current_intent["category"], 
            "brand": current_intent.get("brand"),
            "budget": current_intent.get("budget"), 
            "room_size": current_intent.get("room_size"),
            "family_members": current_intent.get("family_members"),
            "laptop_needs": current_intent.get("laptop_needs"),
            "headphone_needs": current_intent.get("headphone_needs"),
            "phone_needs": current_intent.get("phone_needs"),
            "product_query": user_message if current_keywords else None
        }
    else:
        if current_intent.get("category"):
            accumulated_intent["category"] = current_intent["category"]
        if current_intent.get("brand"):
            accumulated_intent["brand"] = current_intent["brand"]
        if current_intent.get("budget"):
            accumulated_intent["budget"] = current_intent["budget"]
        if current_intent.get("room_size"):
            accumulated_intent["room_size"] = current_intent["room_size"]
        if current_intent.get("family_members"):
            accumulated_intent["family_members"] = current_intent["family_members"]
        if current_intent.get("laptop_needs"):
            accumulated_intent["laptop_needs"] = current_intent["laptop_needs"]
        if current_intent.get("headphone_needs"):
            accumulated_intent["headphone_needs"] = current_intent["headphone_needs"]
        if current_intent.get("phone_needs"):
            accumulated_intent["phone_needs"] = current_intent["phone_needs"]
        if current_keywords:
            accumulated_intent["product_query"] = user_message
        
    category = accumulated_intent.get('category')
    brand = accumulated_intent.get('brand')
    budget = accumulated_intent.get('budget')
    room_size = accumulated_intent.get('room_size')
    family_members = accumulated_intent.get('family_members')
    laptop_needs = accumulated_intent.get('laptop_needs')
    headphone_needs = accumulated_intent.get('headphone_needs')
    phone_needs = accumulated_intent.get('phone_needs')
    room_size = accumulated_intent.get('room_size')
    family_members = accumulated_intent.get('family_members')
    laptop_needs = accumulated_intent.get('laptop_needs')
    headphone_needs = accumulated_intent.get('headphone_needs')
    
    # Xác định chuỗi truy vấn thực tế để tìm kiếm trong DB (tái sử dụng từ khóa cũ nếu tin nhắn hiện tại là lời phản hồi/xác nhận ngắn)
    query_to_search = accumulated_intent.get("product_query") or user_message
    
    # Nhận diện ý định hỏi về chính sách
    policy_keywords = [
        "chính sách", "chinh sach", "đổi trả", "doi tra", "bảo hành", "bao hanh", 
        "giao hàng", "giao hang", "trả góp", "tra gop", "hoàn tiền", "hoan tien", 
        "phí đổi", "phi doi", "lắp đặt", "lap dat", "tổng đài", "tong dai", 
        "khiếu nại", "khieu nai", "phục vụ", "phuc vu", "từ chối", "tu choi", 
        "hạn chế", "han che", "quy định", "quy dinh", "điều khoản", "dieu khoan"
    ]
    cleaned_msg = user_message.lower()
    is_policy_query = any(kw in cleaned_msg for kw in policy_keywords)
    
    policy_context = ""
    if is_policy_query:
        policy_chunks = query_policy(user_message, n_results=3)
        if policy_chunks:
            policy_context = "\n".join([f"- {chunk}" for chunk in policy_chunks])

    # 2. XÁC ĐỊNH LOGIC HỎI LÀM RÕ TIÊU CHÍ (SPEC CLARIFICATION)
    need_clarify = False
    clarify_instruction = ""
    
    if category and not is_policy_query:
        # Kiểm tra từ chối hoặc số lần đã hỏi làm rõ
        refused_clarify = False
        all_user_messages = [msg for msg in history if msg.get("role") == "user"] if history else []
        all_user_messages.append({"role": "user", "content": user_message})
        
        refusal_keywords = ["bỏ qua", "skip", "không cần", "khong can", "không muốn", "khong muon", 
                            "tùy", "tuy", "đại đi", "dai di", "nào cũng được", "nao cung duoc", "bất kỳ", "bat ky"]
        for msg in all_user_messages:
            content_lower = msg.get("content", "").lower()
            if any(kw in content_lower for kw in refusal_keywords):
                refused_clarify = True
                break
                
        # Kiểm tra xem trợ lý đã từng hỏi làm rõ câu nào chưa
        clarify_count = 0
        if history:
            for msg in history:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if any(phrase in content for phrase in [
                        "bao nhiêu m²", "bao nhiêu m2", "bao nhiêu người", 
                        "công việc gì là chủ yếu", "ngân sách dự kiến", 
                        "nhét tai True Wireless", "kiểu dáng", "thương hiệu", "nhu cầu"
                    ]):
                        clarify_count += 1

        # Kiểm tra sự hiện diện của các tiêu chí
        has_brand = brand is not None
        has_budget = budget is not None
        
        category_need = None
        if category == 'may-lanh':
            category_need = room_size
        elif category == 'tu-lanh':
            category_need = family_members
        elif category == 'laptop':
            category_need = laptop_needs
        elif category == 'tai-nghe':
            category_need = headphone_needs
        elif category == 'dien-thoai':
            category_need = phone_needs
            
        has_need = category_need is not None

        # Kiểm tra xem người dùng có hỏi mẫu sản phẩm cụ thể hay không (ví dụ: iPhone 16, S24...)
        is_specific_model = False
        model_keywords = ["pro", "max", "plus", "ultra", "mini", "fold", "flip", "series", "s23", "s24", "iphone 11", "iphone 12", "iphone 13", "iphone 14", "iphone 15", "iphone 16"]
        has_number = any(char.isdigit() for char in cleaned_msg)
        if has_number or any(kw in cleaned_msg for kw in model_keywords):
            is_specific_model = True

        enough_specs = False
        if is_specific_model:
            # Nếu khách tìm mã/mẫu máy cụ thể (ví dụ: iPhone 16, S24...), bỏ qua làm rõ tiêu chí
            enough_specs = True
        elif has_brand:
            # Biết thương hiệu rồi: chỉ cần thêm ít nhất 1 spec nữa (ngân sách hoặc nhu cầu)
            if has_budget or has_need:
                enough_specs = True
        else:
            # Chưa biết thương hiệu: cần có cả ngân sách và nhu cầu (tổng cộng 2 tiêu chí)
            if has_budget and has_need:
                enough_specs = True
                
        # Quy tắc: Cần làm rõ nếu chưa đủ specs, khách chưa từ chối, và số lần hỏi < 2
        need_clarify = not enough_specs and not refused_clarify and clarify_count < 2
        
        if need_clarify:
            # Xác định các tiêu chí còn thiếu để thông báo cho LLM hỏi khách
            missing_parts = []
            if not has_brand:
                missing_parts.append("Thương hiệu sản phẩm (ví dụ: iPhone/Samsung cho điện thoại, Daikin/Panasonic cho máy lạnh, v.v.)")
            if not has_budget:
                missing_parts.append("Mức ngân sách dự kiến (ví dụ: dưới 10 triệu, khoảng 15 triệu, v.v.)")
            if not has_need:
                if category == 'may-lanh':
                    missing_parts.append("Diện tích phòng (m2) (ví dụ: dưới 15m2, 15-20m2, v.v.)")
                elif category == 'tu-lanh':
                    missing_parts.append("Số thành viên sử dụng (ví dụ: 2-3 người, trên 5 người, v.v.)")
                elif category == 'laptop':
                    missing_parts.append("Nhu cầu sử dụng chính (ví dụ: học tập/văn phòng, chơi game, thiết kế đồ họa, lập trình, v.v.)")
                elif category == 'tai-nghe':
                    missing_parts.append("Kiểu dáng hoặc tính năng (ví dụ: tai nghe chụp tai over-ear, nhét tai True Wireless, có chống ồn ANC, v.v.)")
                elif category == 'dien-thoai':
                    missing_parts.append("Nhu cầu tính năng nổi bật (ví dụ: chụp hình đẹp, pin trâu, chơi game mượt, v.v.)")
                    
            if has_brand:
                clarify_instruction = (
                    f"Khách hàng muốn mua {category} hãng {brand.upper()} nhưng chưa cung cấp Ngân sách hay Nhu cầu cụ thể. "
                    f"Bạn BẮT BUỘC phải đặt câu hỏi khéo léo để khách hàng lựa chọn/cung cấp ít nhất 1 trong các thông tin sau: {', '.join(missing_parts)}."
                )
            else:
                if not has_budget and not has_need:
                    clarify_instruction = (
                        f"Khách hàng muốn tư vấn về {category} nhưng chưa cung cấp thêm thông tin nào. "
                        f"Bạn BẮT BUỘC phải đặt câu hỏi khéo léo để khách hàng lựa chọn/cung cấp ít nhất 2 tiêu chí trong số các thông tin sau: {', '.join(missing_parts)}."
                    )
                else:
                    clarify_instruction = (
                        f"Khách hàng muốn tư vấn về {category} (đã biết một số thông tin), nhưng chưa xác định Thương hiệu hay các tiêu chí còn lại. "
                        f"Bạn BẮT BUỘC phải đặt câu hỏi khéo léo để khách hàng lựa chọn/cung cấp thêm ít nhất 1 thông tin nữa trong số các thông tin sau: {', '.join(missing_parts)}."
                    )

    # 3. THỰC HIỆN TRUY VẤN RAG NẾU ĐÃ ĐỦ TIÊU CHÍ (HOẶC BỊ BYPASS LÀM RÕ)
    products = []
    is_upsell = False
    context = ""
    top_relevance = 0
    
    if not need_clarify:
        # Thực hiện truy vấn sản phẩm từ Vector Database bằng chuỗi truy vấn thực tế kết hợp lọc metadata (Hybrid RAG)
        products, is_upsell = query_products(
            query_text=query_to_search,
            category=category,
            brand=brand,
            budget=budget,
            n_results=3
        )
        
        if products:
            context_list = []
            for p in products:
                price = p["sale_price"]
                name = p["name"]
                brand_name = p["brand"]
                cat_name = p["category_name"]
                promotion = p["promotion"]
                outstanding = p["outstanding"]
                spec_product = p["spec_product"]
                
                specs_str = ""
                if spec_product:
                    if isinstance(spec_product, dict):
                        specs_str = " - ".join([f"{k}: {v}" for k, v in spec_product.items()])
                    elif isinstance(spec_product, list):
                        specs_str = " - ".join([str(item) for item in spec_product])
                    else:
                        specs_str = str(spec_product)
                        
                formatted_price_str = format_price(price)
                
                full_text = (
                    f"Sản phẩm: {name}. "
                    f"Thương hiệu: {brand_name or 'Khác'}. "
                    f"Ngành hàng: {cat_name}. "
                    f"Giá: {formatted_price_str}. "
                    f"Thông số: {specs_str}. "
                    f"Mô tả: {outstanding}. "
                    f"Link ảnh sản phẩm (url_image): {p.get('url_image', '')}. "
                    f"Link xem chi tiết (url): {p.get('url', '')}"
                )
                
                stock_info = "Tình trạng tồn kho: Còn hàng (Số lượng: 10 sản phẩm)"
                if promotion and promotion.strip():
                    promo_info = f"Khuyến mãi áp dụng: {promotion}"
                else:
                    promo_info = "Khuyến mãi áp dụng: Không có chương trình khuyến mãi nào"
                    
                enriched_text = f"{full_text}. {stock_info}. {promo_info}."
                context_list.append(enriched_text)
                
            context = "\n".join(context_list)
            # Giả định top_relevance = 5 để LLM tư vấn trực tiếp sản phẩm tìm được
            top_relevance = 5

    # Phương án 1: Bypass LLM khi DB trống (Tránh LLM tự bịa sản phẩm khi không tìm thấy kết quả RAG)
    if category and not context and not is_policy_query and not need_clarify:
        yield "Dạ, hiện tại hệ thống siêu thị Điện Máy Xanh đang tạm hết dòng sản phẩm phù hợp với yêu cầu này của anh/chị. Anh/chị có thể thử thay đổi tầm giá, điều chỉnh nhu cầu hoặc tham khảo các nhóm sản phẩm khác đang sẵn hàng và có nhiều khuyến mãi lớn nhé ạ!"
        return

    # Xây dựng danh sách tin nhắn hội thoại cho API chat
    conversation_messages = []
    if history:
        conversation_messages = history
    else:
        conversation_messages = [{"role": "user", "content": user_message}]

    # Không cần dựng history_context thủ công nữa vì đã dùng API Chat
    history_context = ""

    # Đọc nhanh catalog từ Database để kiểm tra thực tế trong kho có sản phẩm thuộc ngành hàng này hay không
    has_category_products = False
    if category and not need_clarify:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            sql_cond = ""
            if category == 'may-lanh':
                sql_cond = "(c.category_name = 'Máy lạnh' OR p.name ILIKE '%%máy lạnh%%' OR p.name ILIKE '%%điều hòa%%')"
            elif category == 'dien-thoai':
                sql_cond = "(c.category_name = 'Điện thoại' OR p.name ILIKE '%%điện thoại%%' OR p.name ILIKE '%%iphone%%')"
            elif category == 'tu-lanh':
                sql_cond = "(c.category_name = 'Tủ lạnh' OR p.name ILIKE '%%tủ lạnh%%' OR p.name ILIKE '%%tủ mát%%' OR p.name ILIKE '%%tủ đông%%')"
            elif category == 'laptop':
                sql_cond = "(c.category_name = 'Laptop' OR p.name ILIKE '%%laptop%%' OR p.name ILIKE '%%máy tính%%')"
            elif category == 'tai-nghe':
                sql_cond = "(c.category_name = 'Loa, Tai nghe' OR p.name ILIKE '%%tai nghe%%' OR p.name ILIKE '%%airpods%%')"
            
            if sql_cond:
                query = f"""
                    SELECT COUNT(*) 
                    FROM products p
                    LEFT JOIN categories c ON p.category_id = c.category_id
                    WHERE {sql_cond}
                """
                print(f"\n[SQL CHECK CATEGORY]:\n{query}\n")
                cur.execute(query)
                count = cur.fetchone()[0]
                has_category_products = (count > 0)
                
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Lỗi kiểm tra danh mục từ DB: {e}")

    # Nếu phát hiện ngành hàng đó trống trơn trong DB -> Báo hết hàng trực tiếp tại Python (Bypass LLM)
    if category and not has_category_products and not need_clarify:
        yield "Dạ, hiện tại ngành hàng này đang tạm hết hàng trên toàn hệ thống siêu thị Điện Máy Xanh. Anh/chị có thể tham khảo các dòng sản phẩm khác như Tủ lạnh, Laptop, Máy rửa chén đang có sẵn rất nhiều sản phẩm và khuyến mãi lớn ạ!"
        return

    # Nếu không phát hiện ngành hàng nào và không hỏi về chính sách, khách đang chào hỏi hoặc nói chuyện chung chung
    if not category and not is_policy_query:
        system_greeting = """Bạn là một nhân viên tư vấn người Việt Nam chuyên nghiệp tại siêu thị Điện Máy Xanh.
        Khách hàng chưa có nhu cầu mua sắm cụ thể hoặc đang chào hỏi bạn.
        Hãy gửi lời chào thân thiện, nhiệt tình và hỏi xem khách hàng đang cần tìm kiếm dòng sản phẩm nào trong các nhóm sau:
        - Điện thoại
        - Máy lạnh / Điều hòa
        - Tủ lạnh
        - Laptop
        - Tai nghe
        
        Trả lời ngắn gọn, lịch sự bằng Tiếng Việt 100%."""
        for chunk in call_local_llm_stream(system_greeting, messages=conversation_messages):
            yield chunk
        return

    if clarify_instruction:
        system_clarify = f"""Bạn là một nhân viên tư vấn người Việt Nam chuyên nghiệp tại siêu thị Điện Máy Xanh.
        LƯU Ý QUAN TRỌNG: Khách hàng vừa mới chuyển sang hỏi về ngành hàng '{category}' (không còn hỏi về ngành hàng cũ ở các lượt chat trước). Bạn BẮT BUỘC phải tập trung 100% vào ngành hàng mới '{category}' này.
        Nhiệm vụ: {clarify_instruction}
        Hãy phản hồi lịch sự, chào đón khách hàng nồng nhiệt và đặt câu hỏi hỏi ngược khéo léo để lấy thông tin. 
        Bạn có thể nêu một vài thương hiệu nổi tiếng mà Điện Máy Xanh đang kinh doanh cho ngành hàng mới này để làm tăng tính hấp dẫn.
        TUYỆT ĐỐI KHÔNG được nhắc lại hoặc nhầm lẫn sang các sản phẩm/thương hiệu/mức giá của ngành hàng cũ trong lịch sử trò chuyện (như điện thoại cũ).
        BẮT BUỘC trả lời ngắn gọn, thân thiện, 100% bằng Tiếng Việt."""
        
        for chunk in call_local_llm_stream(system_clarify, messages=conversation_messages):
            yield chunk
        return

    # 3. LUỒNG RAG + HARD FILTER (Duy trì logic hiển thị context dự phòng)
    if not context or "Không tìm thấy" in context:
        if category:
            context = "Hiện tại trong kho tạm hết dòng sản phẩm khớp chính xác với ngân sách này của anh chị."
        else:
            context = ""

    # Tạo chỉ dẫn khéo léo bán hàng cận biên
    upsell_instruction = ""
    if is_upsell:
        upsell_instruction = f"LƯU Ý BẮT BUỘC: Khách hàng muốn tìm sản phẩm dưới mức giá {format_price(budget)}, tuy nhiên các sản phẩm trong kho đều có giá cao hơn. Bạn BẮT BUỘC phải khéo léo giải thích rằng tầm giá này đang tạm hết, sau đó giới thiệu 2 phương án thay thế có giá rẻ nhất hiện có (trong dữ liệu trên) làm giải pháp tham khảo chất lượng cao."

    # Chỉ thị làm rõ phụ trợ (khi đã có một số thông tin nhưng vẫn cần khảo sát sâu)
    extra_clarify = ""
    if category == 'may-lanh' and not room_size:
        extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết diện tích phòng. Hãy đề xuất sản phẩm phù hợp ngân sách và đặt câu hỏi khéo léo hỏi thêm diện tích phòng của khách để chốt công suất máy lạnh chuẩn nhất."
    elif category == 'tu-lanh' and not family_members:
        extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết số người sử dụng. Hãy đề xuất sản phẩm phù hợp ngân sách và hỏi thêm về số thành viên sử dụng để chọn dung tích tủ lạnh tối ưu."
    elif category == 'laptop' and not laptop_needs:
        extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết nhu cầu công việc. Hãy đề xuất sản phẩm phù hợp ngân sách và hỏi thêm về nhu cầu sử dụng (như làm văn phòng, học tập hay chơi game, đồ họa) để kiểm tra độ tương thích cấu hình."
    elif category == 'tai-nghe' and not headphone_needs:
        extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết kiểu dáng tai nghe. Hãy đề xuất sản phẩm phù hợp ngân sách và hỏi thêm về kiểu dáng tai nghe yêu thích (nhét tai True Wireless hay chụp tai Over-ear) để tư vấn chuẩn nhất."

    policy_section = ""
    if is_policy_query and policy_context:
        policy_section = f"""
    ---
    DỮ LIỆU CHÍNH SÁCH ĐIỆN MÁY XANH (CÓ THẬT):
    {policy_context}
    ---
    QUY TẮC TRẢ LỜI CHÍNH SÁCH:
    - Hãy dựa vào dữ liệu chính sách ở trên để trả lời câu hỏi của khách hàng về chính sách một cách chính xác nhất.
    - Tuyệt đối không tự bịa đặt ra các quy định chính sách không có trong tài liệu.
    - Nếu không tìm thấy thông tin chính sách liên quan trong dữ liệu trên, hãy hướng dẫn khách hàng liên hệ trực tiếp tổng đài 1900.232.461 để được hỗ trợ nhanh nhất.
        """

    # Xác định các chỉ dẫn động để phá vỡ vòng lặp lặp câu hỏi của LLM cục bộ
    other_products_keywords = ["khác", "còn", "con", "dòng nào", "dong nao", "sản phẩm nào", "san pham nao", "mẫu nào", "mau nao", "lựa chọn", "lua chon"]
    is_asking_for_others = any(kw in user_message.lower() for kw in other_products_keywords)
    other_products_instruction = ""
    if is_asking_for_others:
        other_products_instruction = """
    - LƯU Ý KHẨN CẤP: Khách hàng đang hỏi tìm các sản phẩm khác hoặc lựa chọn khác. Bạn BẮT BUỘC phải đọc kỹ context ở trên và liệt kê, giới thiệu toàn bộ các sản phẩm khác (như dòng Pro Max, Pro, v.v.) đang có sẵn trong context. TUYỆT ĐỐI KHÔNG được lặp lại câu hỏi lựa chọn đơn lẻ cũ."""
        
    is_confirmation = user_message.lower() in ["có", "co", "đúng", "dung", "đúng vậy", "ok", "yes", "uh", "ừ", "u", "muốn", "xem đi", "tư vấn đi", "tiếp"]
    was_assistant_asking = False
    if history:
        assistant_msgs = [msg for msg in history if msg.get("role") == "assistant"]
        if assistant_msgs:
            last_content = assistant_msgs[-1].get("content", "").lower()
            if any(phrase in last_content for phrase in ["không?", "không ạ?", "được không", "đúng không", "quan tâm"]):
                was_assistant_asking = True
                
    confirmation_instruction = ""
    if is_confirmation and was_assistant_asking:
        confirmation_instruction = """
    - LƯU Ý KHẨN CẤP: Khách hàng đã đồng ý tư vấn (nhắn 'có' hoặc tương đương). Bạn BẮT BUỘC phải đi thẳng vào chi tiết sản phẩm ngay lập tức: cung cấp giá bán, tình trạng tồn kho, và các quà tặng khuyến mãi chi tiết của sản phẩm có trong context. TUYỆT ĐỐI KHÔNG được hỏi lại câu hỏi cũ dạng 'tôi có thể tư vấn... không?' hoặc 'bạn quan tâm không?'."""

    # 4. PROMPT DỊCH THUẬT BÌNH DÂN & TRADE-OFF (Ăn điểm đặc thù 20%)
    system_advisor = f"""Bạn là một nhân viên tư vấn người Việt Nam chuyên nghiệp tại siêu thị Điện Máy Xanh.
    Hãy dùng tập dữ liệu sản phẩm CÓ THẬT sau đây để tư vấn cho khách:
    ---
    {context}
    ---
    {policy_section}
    
    QUY TẮC TƯ VẤN BẮT BUỘC SỐNG CÒN:
    1. BẮT BUỘC TRẢ LỜI BẰNG TIẾNG VIỆT 100%. TUYỆT ĐỐI KHÔNG dùng tiếng Trung, không dùng chữ Hán.
    2. Chỉ được dùng thông tin sản phẩm, giá bán, tình trạng tồn kho và khuyến mãi có trong dữ liệu ở trên để tư vấn. KHÔNG TỰ BỊA SẢN PHẨM, GIÁ, THÔNG SỐ, KHUYẾN MÃI HOẶC TỒN KHO. Nếu dữ liệu ở trên trống hoặc báo hết hàng (và câu hỏi không phải về chính sách), bạn BẮT BUỘC phải thông báo thành thật rằng sản phẩm đang tạm hết hàng trên hệ thống và KHÔNG giới thiệu bất kỳ sản phẩm nào khác ngoài danh sách.
    3. TUYỆT ĐỐI KHÔNG trộn lẫn thông tin hoặc lấy các sản phẩm cũ trong lịch sử trò chuyện (ví dụ: các dòng điện thoại đã thảo luận ở lượt chat trước) để giới thiệu hay chế biến thành sản phẩm của danh mục mới (ví dụ: tủ lạnh). Mỗi lượt phản hồi chỉ được dùng đúng các sản phẩm được liệt kê trong phần context ở trên. Nếu context chỉ có 1 tủ lạnh Sharp, chỉ tư vấn duy nhất tủ lạnh Sharp đó, tuyệt đối không được tự bịa ra tủ lạnh Samsung sử dụng camera hay các thông số điện thoại từ lịch sử.
    4. Không dùng từ ngữ kỹ thuật phức tạp (như Inverter, HP, BTU). Hãy dịch sang ngôn ngữ bình dân (Ví dụ: 'Máy chạy siêu êm ban đêm', 'Tiết kiệm tiền điện cuối tháng', 'Làm mát nhanh sâu').
    5. Luôn nêu rõ ưu và nhược điểm (Trade-off) giữa các lựa chọn để khách hàng dễ ra quyết định.
    6. BẮT BUỘC THÔNG BÁO cụ thể cho khách hàng về Tình trạng tồn kho thực tế và các chương trình Khuyến mãi/Quà tặng đi kèm của từng sản phẩm dựa trên thông tin thực tế được cung cấp.
    7. ĐỘ DÀI VÀ PHONG CÁCH PHẢN HỒI: Hãy phản hồi cực kỳ ngắn gọn, cô đọng, giới hạn câu trả lời dưới 150-180 từ. Trình bày dưới dạng các đầu dòng rõ ràng để giúp phản hồi sinh ra tức thì (vì chạy cục bộ trên CPU).
    8. QUY TẮC TRÌNH BÀY VÀ ĐƯỜNG DẪN UX (TỐI ƯU TRẢI NGHIỆM):
       - GIÁ TIỀN: BẮT BUỘC luôn luôn làm nổi bật giá tiền bằng cách tăng 1 size chữ và in đậm bằng thẻ span: `<span style="font-size: 1.15em;">**[Giá tiền]đ**</span>`. Ví dụ: `<span style="font-size: 1.15em;">**3.850.000đ**</span>`.
       - ĐỊNH DẠNG TRÌNH BÀY BẮT BUỘC (Theo mẫu trực quan):
         Anh chị tham khảo sản phẩm [Tên sản phẩm] giá [Giá tiền đã bọc thẻ span] ạ.
         - Dung tích (hoặc Diện tích phòng, Nhu cầu tùy ngành hàng): [Giá trị phù hợp]
         - Tiện ích: [Tiện ích chính dịch sang ngôn ngữ bình dân]
         [Thông tin tồn kho và khuyến mãi nếu có]
         
         [Xem chi tiết sản phẩm tại Điện Máy Xanh](url)
         ![ảnh sản phẩm](url_image)
         Anh/chị có quan tâm không ạ?
       - Bạn chỉ được chèn link xem chi tiết và ảnh nếu có trong context (trường 'url' và 'url_image'), tuyệt đối không tự bịa link.
    {other_products_instruction}
    {confirmation_instruction}
    
    {upsell_instruction}
    {extra_clarify}
    Hãy bắt đầu bằng một lời chào lịch sự thân thiện."""

    for chunk in call_local_llm_stream(system_advisor, messages=conversation_messages, is_recommendation=not is_policy_query):
        yield chunk
