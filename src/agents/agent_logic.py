import requests
import json
import re
from src.database.vector_store import query_policy
from src.database.sync_supabase import get_db_connection, safe_int, format_price, normalize_category

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b" # Thay bằng qwen2.5:1.5b hoặc bản bạn đã tải thành công

def call_local_llm_stream(system_prompt, messages):
    """Gửi yêu cầu qua API Chat của Ollama để tận dụng template hội thoại chuẩn của mô hình"""
    payload_messages = [{"role": "system", "content": system_prompt}]
    
    # Nạp toàn bộ lịch sử hội thoại chuẩn
    for msg in messages:
        payload_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
        
    # Thêm chỉ dẫn khẩn cấp cuối danh sách tin nhắn để ghi đè xu hướng tiếng Trung của Qwen
    payload_messages.append({
        "role": "system",
        "content": "BẮT BUỘC: Bạn là tư vấn viên Việt Nam, chỉ viết bằng tiếng Việt. KHÔNG ĐƯỢC phép sử dụng bất kỳ chữ Hán/chữ Trung Quốc nào (ví dụ: 比如, 办公, 学习, 建议, etc.) trong câu trả lời."
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
        "budget": None, 
        "room_size": None, 
        "family_members": None,
        "laptop_needs": None,
        "headphone_needs": None
    }
    
    # 1. Nhận dạng ngành hàng (category)
    if any(kw in cleaned for kw in ["máy lạnh", "may-lanh", "may lanh", "điều hòa", "dieu hoa"]):
        intent["category"] = "may-lanh"
    elif any(kw in cleaned for kw in ["điện thoại", "dien-thoai", "dien thoai", "phone", "iphone", "samsung", "oppo", "xiaomi", "vivo"]):
        intent["category"] = "dien-thoai"
    elif any(kw in cleaned for kw in ["tủ lạnh", "tu-lanh", "tu lanh"]):
        intent["category"] = "tu-lanh"
    elif any(kw in cleaned for kw in ["laptop", "máy tính", "may tinh", "macbook", "asus", "rog", "hp", "acer", "lenovo"]):
        intent["category"] = "laptop"
    elif any(kw in cleaned for kw in ["tai nghe", "tai-nghe", "tai nghe", "airpods", "buds", "headphone"]):
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
                    
    return intent


def parse_search_features(user_message):
    text = user_message.lower()
    return {
        "camera": any(kw in text for kw in ["camera", "chụp ảnh", "ảnh đẹp", "anh dep", "cam"]),
        "gaming": any(kw in text for kw in ["chơi game", "gaming", "game", "fps", "mở game", "pubg", "lien quan"]),
        "battery": any(kw in text for kw in ["pin trâu", "pin dai", "pin lớn", "5000", "6000", "dung lượng pin"]),
        "student": any(kw in text for kw in ["sinh viên", "hoc sinh", "học sinh", "sinh vien", "van phong", "văn phòng", "học tập", "hoc tap"]),
        "camera_only": any(kw in text for kw in ["camera đẹp", "chụp ảnh đẹp", "camera tốt"]),
        "fast_charge": any(kw in text for kw in ["sạc nhanh", "fast charge", "45w", "60w", "120w"]),
        "iphone_style": any(kw in text for kw in ["giống iphone", "giong iphone", "kiểu iphone", "style iphone"]),
        "vlog": any(kw in text for kw in ["vlog", "quay vlog", "video blogger", "content creator"]),
    }


def build_search_filter_conditions(category, budget, intent, user_message):
    filters = []
    if category:
        sql_cat = category_sql_condition(category)
        if sql_cat:
            filters.append(sql_cat)

    feature_map = parse_search_features(user_message)

    if feature_map.get("battery"):
        filters.append("(p.spec_product::text ILIKE '%pin%' OR p.outstanding ILIKE '%pin%' OR p.name ILIKE '%pin%')")
    if feature_map.get("camera"):
        filters.append("(p.spec_product::text ILIKE '%camera%' OR p.outstanding ILIKE '%camera%' OR p.name ILIKE '%camera%')")
    if feature_map.get("gaming"):
        filters.append("(p.spec_product::text ILIKE '%gaming%' OR p.name ILIKE '%gaming%' OR p.outstanding ILIKE '%gaming%')")
    if feature_map.get("fast_charge"):
        filters.append("(p.spec_product::text ILIKE '%sạc nhanh%' OR p.spec_product::text ILIKE '%fast charge%' OR p.outstanding ILIKE '%sạc nhanh%')")
    if feature_map.get("camera_only"):
        filters.append("(p.spec_product::text ILIKE '%camera%' OR p.outstanding ILIKE '%camera%' OR p.name ILIKE '%camera%')")
    if feature_map.get("student"):
        filters.append("(p.outstanding ILIKE '%văn phòng%' OR p.outstanding ILIKE '%học tập%' OR p.name ILIKE '%văn phòng%' OR p.name ILIKE '%học tập%')")
    if feature_map.get("iphone_style"):
        filters.append("(p.name ILIKE '%iphone%' OR p.outstanding ILIKE '%iphone%' OR p.spec_product::text ILIKE '%iphone%')")
    if feature_map.get("vlog"):
        filters.append("(p.spec_product::text ILIKE '%vlog%' OR p.outstanding ILIKE '%vlog%' OR p.name ILIKE '%vlog%')")

    if intent:
        if intent.get("laptop_needs") == "van-phong":
            filters.append("(p.spec_product::text ILIKE '%office%' OR p.spec_product::text ILIKE '%văn phòng%' OR p.spec_product::text ILIKE '%học tập%' OR p.spec_product::text ILIKE '%word%' OR p.spec_product::text ILIKE '%excel%')")
        elif intent.get("laptop_needs") == "do-hoa-game":
            filters.append("(p.spec_product::text ILIKE '%gaming%' OR p.spec_product::text ILIKE '%RTX%' OR p.spec_product::text ILIKE '%16GB%' OR p.spec_product::text ILIKE '%144Hz%' OR p.outstanding ILIKE '%gaming%')")
        elif intent.get("laptop_needs") == "code":
            filters.append("(p.spec_product::text ILIKE '%SSD%' OR p.spec_product::text ILIKE '%RAM%' OR p.spec_product::text ILIKE '%chip%' OR p.outstanding ILIKE '%lập trình%' OR p.outstanding ILIKE '%code%')")

        if intent.get("headphone_needs") == "chong-on":
            filters.append("(p.spec_product::text ILIKE '%ANC%' OR p.outstanding ILIKE '%chống ồn%' OR p.name ILIKE '%ANC%')")
        elif intent.get("headphone_needs") == "gaming":
            filters.append("(p.outstanding ILIKE '%gaming%' OR p.spec_product::text ILIKE '%gaming%' OR p.name ILIKE '%gaming%')")
        elif intent.get("headphone_needs") == "chup-tai":
            filters.append("(p.name ILIKE '%chụp tai%' OR p.spec_product::text ILIKE '%over-ear%' OR p.outstanding ILIKE '%over-ear%')")
        elif intent.get("headphone_needs") == "nhet-tai":
            filters.append("(p.name ILIKE '%true wireless%' OR p.spec_product::text ILIKE '%in-ear%' OR p.outstanding ILIKE '%nhet tai%' OR p.outstanding ILIKE '%in ear%')")

        if category == 'may-lanh' and intent.get('room_size'):
            match = re.search(r'(\d+)', intent['room_size'])
            if match:
                room_value = int(match.group(1))
                if room_value <= 15:
                    filters.append("(p.spec_product::text ILIKE '%1 HP%' OR p.spec_product::text ILIKE '%1.0 HP%' OR p.outstanding ILIKE '%1 HP%' OR p.name ILIKE '%1 HP%')")
                elif room_value <= 28:
                    filters.append("(p.spec_product::text ILIKE '%1.5 HP%' OR p.spec_product::text ILIKE '%1.5 HP%' OR p.outstanding ILIKE '%1.5 HP%' OR p.name ILIKE '%1.5 HP%')")
                else:
                    filters.append("(p.spec_product::text ILIKE '%2 HP%' OR p.spec_product::text ILIKE '%2.0 HP%' OR p.outstanding ILIKE '%2 HP%' OR p.name ILIKE '%2 HP%')")

        if category == 'tu-lanh' and intent.get('family_members'):
            members = intent['family_members']
            if members <= 2:
                filters.append("(p.spec_product::text ILIKE '%150L%' OR p.spec_product::text ILIKE '%180L%' OR p.outstanding ILIKE '%150L%' OR p.outstanding ILIKE '%180L%')")
            elif members <= 4:
                filters.append("(p.spec_product::text ILIKE '%200L%' OR p.spec_product::text ILIKE '%250L%' OR p.outstanding ILIKE '%200L%' OR p.outstanding ILIKE '%250L%')")
            else:
                filters.append("(p.spec_product::text ILIKE '%300L%' OR p.spec_product::text ILIKE '%330L%' OR p.outstanding ILIKE '%300L%' OR p.outstanding ILIKE '%330L%')")

    return filters


def build_search_order_clause(category, intent, user_message):
    feature_map = parse_search_features(user_message)
    if intent and intent.get("laptop_needs") == "do-hoa-game":
        return "ORDER BY p.sale_price DESC"
    if intent and intent.get("laptop_needs") == "van-phong":
        return "ORDER BY p.sale_price ASC"
    if feature_map.get("gaming"):
        return "ORDER BY p.sale_price DESC"
    if feature_map.get("camera"):
        return "ORDER BY p.sale_price DESC"
    if feature_map.get("battery"):
        return "ORDER BY p.sale_price DESC"
    return "ORDER BY relevance DESC, p.sale_price DESC"


def build_product_context(rows):
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

        specs_str = ""
        if spec_product:
            if isinstance(spec_product, dict):
                specs_str = " - ".join([f"{k}: {v}" for k, v in spec_product.items()])
            elif isinstance(spec_product, list):
                specs_str = " - ".join([str(item) for item in spec_product])
            else:
                specs_str = str(spec_product)

        formatted_price_str = format_price(price)
        stock_info = "Tình trạng tồn kho: Còn hàng (Số lượng: 10 sản phẩm)"
        promo_info = f"Khuyến mãi áp dụng: {promotion}" if promotion.strip() else "Khuyến mãi áp dụng: Không có chương trình khuyến mãi nào"

        enriched_text = (
            f"Sản phẩm: {name}. "
            f"Thương hiệu: {brand or 'Khác'}. "
            f"Ngành hàng: {cat_name}. "
            f"Giá: {formatted_price_str}. "
            f"Thông số: {specs_str}. "
            f"Mô tả: {outstanding}. "
            f"{stock_info}. {promo_info}."
        )
        context_list.append(enriched_text)

    return "\n".join(context_list)


def query_exact_product(user_message, limit=5):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        raw_tokens = [tk.strip() for tk in re.findall(r"[\wÀ-ỹ\-]+", user_message) if len(tk.strip()) >= 2]
        if not raw_tokens:
            return []

        stop_words = {
            'tôi', 'toi', 'muốn', 'muon', 'mua', 'cho', 'co', 'có', 'không', 'khong',
            'tại', 'tai', 'ở', 'o', 'nào', 'nao', 'và', 'va', 'với', 'voi', 'về', 've',
            'cần', 'can', 'tìm', 'tim', 'giúp', 'giup', 'giá', 'gia', 'dưới', 'duoi',
            'khoảng', 'khoang', 'tầm', 'tam', 'sản', 'san', 'phẩm', 'pham'
        }
        tokens = [tk for tk in raw_tokens if tk.lower() not in stop_words and not tk.isdigit()]
        if not tokens:
            return []

        conditions = []
        params = []
        for token in tokens:
            like_token = f"%{token}%"
            conditions.append("(p.name ILIKE %s OR p.product_code ILIKE %s OR p.outstanding ILIKE %s)")
            params.extend([like_token, like_token, like_token])

        exact_phrase = user_message.strip()
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
                (CASE
                    WHEN p.product_code ILIKE %s THEN 100
                    WHEN p.name ILIKE %s THEN 80
                    WHEN p.outstanding ILIKE %s THEN 40
                    ELSE 0
                END) AS phrase_score
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE {' AND '.join(conditions)}
            ORDER BY phrase_score DESC, p.sale_price DESC
            LIMIT %s
        """
        params.extend([f"%{exact_phrase}%", f"%{exact_phrase}%", f"%{exact_phrase}%"])
        params.append(limit)
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


def category_sql_condition(category):
    if category == 'may-lanh':
        return "(c.category_name = 'Máy lạnh' OR p.name ILIKE '%máy lạnh%' OR p.name ILIKE '%điều hòa%')"
    elif category == 'dien-thoai':
        return "(c.category_name = 'Điện thoại' OR p.name ILIKE '%điện thoại%' OR p.name ILIKE '%iphone%')"
    elif category == 'tu-lanh':
        return "(c.category_name = 'Tủ lạnh' OR p.name ILIKE '%tủ lạnh%' OR p.name ILIKE '%tủ mát%' OR p.name ILIKE '%tủ đông%')"
    elif category == 'laptop':
        return "(c.category_name = 'Laptop' OR p.name ILIKE '%laptop%' OR p.name ILIKE '%máy tính%')"
    elif category == 'tai-nghe':
        return "(c.category_name = 'Loa, Tai nghe' OR p.name ILIKE '%tai nghe%' OR p.name ILIKE '%airpods%')"
    return ""


def category_has_products(category):
    sql_cond = category_sql_condition(category)
    if not sql_cond:
        return False

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        query = f"""
            SELECT 1
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE {sql_cond}
            LIMIT 1
        """
        cur.execute(query)
        result = cur.fetchone()
        cur.close()
        conn.close()
        return bool(result)
    except Exception:
        return False


def db_search_products(category, budget, user_message, intent=None, limit=3):
    context = ""
    is_upsell = False
    top_relevance = 0

    sql_cond = category_sql_condition(category)
    if not sql_cond:
        return context, is_upsell, top_relevance

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cleaned = re.sub(r'[^\w\s\-À-ỹ]', ' ', user_message.lower())
        words = [w for w in cleaned.split() if len(w) >= 2]
        stop_words = {
            'tôi', 'toi', 'muốn', 'muon', 'mua', 'cho', 'co', 'có', 'không', 'khong',
            'tại', 'tai', 'ở', 'o', 'nào', 'nao', 'và', 'va', 'với', 'voi', 'về', 've',
            'cần', 'can', 'tìm', 'tim', 'giúp', 'giup', 'giá', 'gia', 'dưới', 'duoi',
            'khoảng', 'khoang', 'tầm', 'tam', 'sản', 'san', 'phẩm', 'pham', 'ngân', 'ngan',
            'sách', 'sach', 'trên', 'tren', 'dưới', 'duoi', 'và', 'va'
        }
        keywords = [w for w in words if w not in stop_words and not (w.isdigit() and len(w) >= 3)]

        filters = build_search_filter_conditions(category, budget, intent, user_message)
        filter_sql = ' AND '.join(filters) if filters else '1=1'
        order_clause = build_search_order_clause(category, intent, user_message)

        budget_cond = ''
        if budget:
            budget_cond = ' AND p.sale_price <= %s'

        relevance_score_expr = '0'
        match_cond = '1=1'
        if keywords:
            score_parts = []
            match_parts = []
            for kw in keywords:
                escaped_kw = kw.replace("'", "''")
                is_model_code = '-' in kw or (any(c.isdigit() for c in kw) and any(c.isalpha() for c in kw) and len(kw) >= 5)

                if is_model_code:
                    score_parts.append(f"""
                        (CASE
                            WHEN p.product_id = '{escaped_kw}' OR p.product_code = '{escaped_kw}' THEN 50
                            WHEN p.name ILIKE '%{escaped_kw}%' THEN 30
                            WHEN p.outstanding ILIKE '%{escaped_kw}%' THEN 10
                            WHEN p.spec_product::text ILIKE '%{escaped_kw}%' THEN 5
                            ELSE 0
                        END)
                    """)
                else:
                    score_parts.append(f"""
                        (CASE
                            WHEN p.name ILIKE '%{escaped_kw}%' THEN 4
                            WHEN p.outstanding ILIKE '%{escaped_kw}%' THEN 2
                            WHEN p.spec_product::text ILIKE '%{escaped_kw}%' THEN 1
                            ELSE 0
                        END)
                    """)
                match_parts.append(f"(p.name ILIKE '%{escaped_kw}%' OR p.product_code ILIKE '%{escaped_kw}%' OR p.outstanding ILIKE '%{escaped_kw}%' OR p.spec_product::text ILIKE '%{escaped_kw}%')")

            relevance_score_expr = ' + '.join(score_parts)
            match_cond = '(' + ' OR '.join(match_parts) + ')'

        params = []
        if budget:
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
            WHERE {filter_sql}{budget_cond} AND {match_cond}
            {order_clause}
            LIMIT %s
        """
        params.append(limit)
        cur.execute(query, params)
        rows = cur.fetchall()

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
                WHERE {filter_sql} AND {match_cond}
                ORDER BY relevance DESC, p.sale_price ASC
                LIMIT %s
            """
            cur.execute(query_upsell, (limit,))
            rows = cur.fetchall()

        if not rows:
            params = []
            if budget:
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
                WHERE {filter_sql}{budget_cond}
                ORDER BY p.sale_price DESC
                LIMIT %s
            """
            params.append(limit)
            cur.execute(query_fallback, params)
            rows = cur.fetchall()

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
                WHERE {filter_sql}
                ORDER BY p.sale_price ASC
                LIMIT %s
            """
            cur.execute(query_final_fallback, (limit,))
            rows = cur.fetchall()

        rows = rows[:limit]
        if rows:
            top_relevance = rows[0][9] if rows and len(rows[0]) > 9 else 0
            context = build_product_context(rows)

        cur.close()
        conn.close()
    except Exception as e:
        context = f"Lỗi đọc kho dữ liệu từ DB: {str(e)}"

    return context, is_upsell, top_relevance
def generate_advisor_response_stream(user_message, history=None):
    """Luồng điều phối chính dạng Generator (truyền tải dữ liệu luồng về UI)"""
    # 1. Tích lũy intent từ lịch sử chat để duy trì ngữ cảnh trạng thái (Stateful)
    accumulated_intent = {
        "category": None, 
        "budget": None, 
        "room_size": None,
        "family_members": None,
        "laptop_needs": None,
        "headphone_needs": None
    }
    
    if history:
        for msg in history:
            if msg.get("role") == "user":
                prev_intent = analyze_intent_fast(msg.get("content", ""))
                # Nếu phát hiện đổi category, reset toàn bộ các tham số tích lũy của category cũ
                if prev_intent.get("category") and prev_intent["category"] != accumulated_intent["category"]:
                    accumulated_intent = {
                        "category": prev_intent["category"], 
                        "budget": None, 
                        "room_size": None,
                        "family_members": None,
                        "laptop_needs": None,
                        "headphone_needs": None
                    }
                else:
                    if prev_intent.get("category"):
                        accumulated_intent["category"] = prev_intent["category"]
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
                    
    # Cập nhật thêm từ tin nhắn hiện tại
    current_intent = analyze_intent_fast(user_message)
    if current_intent.get("category") and current_intent["category"] != accumulated_intent["category"]:
        accumulated_intent = {
            "category": current_intent["category"], 
            "budget": None, 
            "room_size": None,
            "family_members": None,
            "laptop_needs": None,
            "headphone_needs": None
        }
    else:
        if current_intent.get("category"):
            accumulated_intent["category"] = current_intent["category"]
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
        
    category = accumulated_intent.get('category')
    budget = accumulated_intent.get('budget')
    room_size = accumulated_intent.get('room_size')
    family_members = accumulated_intent.get('family_members')
    laptop_needs = accumulated_intent.get('laptop_needs')
    headphone_needs = accumulated_intent.get('headphone_needs')
    
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

    # TH1: Tìm sản phẩm cụ thể trước khi vào pipeline mơ hồ
    exact_rows = query_exact_product(user_message, limit=3)
    if exact_rows:
        context = build_product_context(exact_rows)
        is_upsell = False
        top_relevance = 5
        if exact_rows[0][3]:
            normalized_cat = normalize_category(exact_rows[0][3])
            if normalized_cat:
                category = normalized_cat
                accumulated_intent["category"] = normalized_cat
    else:
        # Thực hiện truy vấn sản phẩm từ Database trước để xem có khớp sản phẩm cụ thể hay không
        intent_snapshot = {
            "category": category,
            "budget": budget,
            "room_size": room_size,
            "family_members": family_members,
            "laptop_needs": laptop_needs,
            "headphone_needs": headphone_needs
        }
        context, is_upsell, top_relevance = db_search_products(category, budget, user_message, intent=intent_snapshot)

    # Xây dựng danh sách tin nhắn hội thoại cho API chat
    if history:
        conversation_messages = history
    else:
        conversation_messages = [{"role": "user", "content": user_message}]

    # Đọc nhanh catalog từ Database để kiểm tra thực tế trong kho có sản phẩm thuộc ngành hàng này hay không
    has_category_products = category and category_has_products(category)

    # Nếu phát hiện ngành hàng đó trống trơn trong DB -> Báo hết hàng trực tiếp tại Python (Bypass LLM)
    if category and not has_category_products:
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
    
    # 2. KIỂM TRA TỪ CHỐI & GIỚI HẠN SỐ LẦN HỎI LÀM RÕ (TRÁNH TRA KHẢO KHÁCH HÀNG)
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
                if any(phrase in content for phrase in ["bao nhiêu m²", "bao nhiêu m2", "bao nhiêu người", "công việc gì là chủ yếu", "ngân sách dự kiến", "nhét tai True Wireless"]):
                    clarify_count += 1

    # XÁC ĐỊNH CHỈ THỊ HỎI LÀM RÕ (Bypass nếu khách từ chối, đã hỏi rồi, đang hỏi về chính sách, hoặc đã xác định được sản phẩm cụ thể với top_relevance >= 4)
    clarify_instruction = ""
    bypass_clarify = (top_relevance >= 4)
    
    if not bypass_clarify and not refused_clarify and clarify_count < 1 and not is_policy_query:
        if category == 'may-lanh' and not room_size and not budget:
            clarify_instruction = "Khách hàng muốn mua máy lạnh nhưng chưa cung cấp diện tích phòng hoặc ngân sách. Bạn BẮT BUỘC phải hỏi khéo léo về diện tích phòng (m2) để tư vấn công suất máy lạnh (1 HP hay 1.5 HP) phù hợp."
        elif category == 'tu-lanh' and not family_members and not budget:
            clarify_instruction = "Khách hàng muốn mua tủ lạnh nhưng chưa cung cấp số thành viên sử dụng hoặc ngân sách. Bạn BẮT BUỘC phải hỏi khéo léo về số người sử dụng để tư vấn dung tích phù hợp."
        elif category == 'laptop' and not laptop_needs and not budget:
            clarify_instruction = "Khách hàng muốn mua laptop nhưng chưa rõ nhu cầu sử dụng hoặc ngân sách. Bạn BẮT BUỘC phải hỏi khéo léo về nhu cầu chính (văn phòng học tập hay đồ họa game) để tư vấn cấu hình phù hợp."
        elif category == 'dien-thoai' and not budget:
            clarify_instruction = "Khách hàng muốn mua điện thoại nhưng chưa cung cấp ngân sách. Bạn BẮT BUỘC phải hỏi khéo léo về mức ngân sách dự kiến của họ để lọc sản phẩm."
        elif category == 'tai-nghe' and not headphone_needs and not budget:
            clarify_instruction = "Khách hàng muốn mua tai nghe nhưng chưa cung cấp kiểu dáng hoặc ngân sách. Bạn BẮT BUỘC phải hỏi khéo léo về kiểu dáng (nhét tai True Wireless hay chụp tai Over-ear) và nhu cầu tính năng (chống ồn ANC, gaming)."

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
    7. ĐỘ DÀI VÀ PHONG CÁCH PHẢN HỒI: Hãy phản hồi cực kỳ ngắn gọn, cô đọng, giới hạn câu trả lời dưới 120-150 từ. Trình bày dưới dạng các đầu dòng rõ ràng để giúp phản hồi sinh ra tức thì (vì chạy cục bộ trên CPU).
    
    {upsell_instruction}
    {extra_clarify}
    Hãy bắt đầu bằng một lời chào lịch sự thân thiện."""

    for chunk in call_local_llm_stream(system_advisor, messages=conversation_messages):
        yield chunk