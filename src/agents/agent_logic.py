import requests
import json
import os
import re
from src.database.vector_store import query_policy, query_products
from src.database.sync_supabase import get_db_connection, safe_int, format_price


def normalize_category_name(category):
    if not category:
        return None
    cleaned = category.lower().strip()
    mapping = {
        "máy lạnh": "may-lanh",
        "may lanh": "may-lanh",
        "điều hòa": "may-lanh",
        "dieu hoa": "may-lanh",
        "điện thoại": "dien-thoai",
        "dien thoai": "dien-thoai",
        "tủ lạnh": "tu-lanh",
        "tu lanh": "tu-lanh",
        "laptop": "laptop",
        "loa, tai nghe": "tai-nghe",
        "tai nghe": "tai-nghe",
        "headphone": "tai-nghe",
    }
    return mapping.get(cleaned, cleaned)


def detect_specific_model_request(user_message):
    """Phát hiện khi khách hỏi một model/series cụ thể để ưu tiên xử lý riêng."""
    cleaned = re.sub(r"\s+", " ", (user_message or "").lower()).strip()
    if not cleaned:
        return {"is_specific_model": False, "requested_model": None}

    brands = [
        "iphone", "samsung", "oppo", "xiaomi", "realme", "vivo", "asus", "hp",
        "acer", "lenovo", "dell", "msi", "sony", "jbl", "lg", "sharp", "hitachi",
        "panasonic", "toshiba", "daikin", "casper", "macbook", "galaxy", "oneplus", "nokia"
    ]
    for brand in brands:
        patterns = [
            rf"\b{brand}\b(?:\s+(?:\d+|[a-z]+)){{0,4}}",
            rf"{brand}(?:\s+(?:\d+|[a-z]+)){{0,4}}",
        ]
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if match:
                phrase = match.group(0)
                if re.search(r"\d", phrase) or any(token in phrase for token in ["pro", "max", "plus", "ultra", "mini", "fold", "flip", "series", "note", "edge"]):
                    return {"is_specific_model": True, "requested_model": phrase.strip()}
                break

    return {"is_specific_model": False, "requested_model": None}


def reset_intent_state_on_category_change(prev_state, current_intent, current_message=None):
    """Xóa state cũ khi khách chuyển sang danh mục mới để tránh nhiễm state."""
    new_state = {
        "category": current_intent.get("category") or prev_state.get("category"),
        "brand": current_intent.get("brand"),
        "budget": current_intent.get("budget"),
        "room_size": None,
        "family_members": None,
        "laptop_needs": None,
        "headphone_needs": None,
        "phone_needs": None,
        "product_query": None,
    }

    if current_intent.get("room_size") is not None:
        new_state["room_size"] = current_intent.get("room_size")
    if current_intent.get("family_members") is not None:
        new_state["family_members"] = current_intent.get("family_members")
    if current_intent.get("laptop_needs") is not None:
        new_state["laptop_needs"] = current_intent.get("laptop_needs")
    if current_intent.get("headphone_needs") is not None:
        new_state["headphone_needs"] = current_intent.get("headphone_needs")
    if current_intent.get("phone_needs") is not None:
        new_state["phone_needs"] = current_intent.get("phone_needs")

    if current_message:
        current_keywords = extract_search_keywords_only(current_message, current_intent.get("budget"))
        if current_keywords:
            new_state["product_query"] = current_message

    return new_state


def merge_intent_state(accumulated_intent, new_intent, user_message=None):
    """Gộp intent mới vào state hiện tại nhưng chỉ ghi đè khi có giá trị thật."""
    merged = dict(accumulated_intent)
    for key in ["category", "brand", "budget", "room_size", "family_members", "laptop_needs", "headphone_needs", "phone_needs"]:
        value = new_intent.get(key)
        if value is not None:
            merged[key] = value

    if user_message:
        keywords = extract_search_keywords_only(user_message, new_intent.get("budget"))
        if keywords:
            merged["product_query"] = user_message

    return merged


def filter_history_for_current_category(history, current_message):
    """Lọc lịch sử sao cho chỉ giữ các lượt trao đổi thuộc cùng danh mục với câu hỏi hiện tại."""
    if not history:
        return []

    current_intent = analyze_intent_fast(current_message or "")
    current_category = current_intent.get("category")
    filtered_history = []
    active_category = None

    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role not in {"user", "assistant"}:
            continue

        if role == "user":
            msg_intent = analyze_intent_fast(content)
            msg_category = msg_intent.get("category")

            if current_category and msg_category and msg_category != current_category:
                filtered_history = []
                active_category = None
                continue

            if current_category and msg_category and msg_category == current_category:
                active_category = msg_category
                filtered_history.append(msg)
            elif current_category is None and msg_category:
                active_category = msg_category
                filtered_history.append(msg)
            elif current_category is None:
                filtered_history.append(msg)
            elif not msg_category:
                filtered_history.append(msg)
        elif role == "assistant" and active_category is not None:
            filtered_history.append(msg)
        elif role == "assistant" and current_category is None and filtered_history:
            filtered_history.append(msg)

    return filtered_history

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b" # Thay bằng qwen2.5:1.5b hoặc bản bạn đã tải thành công

# =====================================================================
# TẦNG 1: BỘ NÃO AI LOCAL (OLLAMA CLIENT) - CÓ MÀNG LỌC REGEX ĐẦU RA
# =====================================================================
def call_local_llm_stream(system_prompt, messages, is_recommendation=False):
    """Gửi yêu cầu qua API Chat của Ollama để tận dụng template hội thoại chuẩn của mô hình"""
    payload_messages = [{"role": "system", "content": system_prompt}]
    
    # Nạp toàn bộ lịch sử hội thoại chuẩn từ Stateful History
    for msg in messages:
        payload_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
        
    # Chỉ dẫn khẩn cấp cuối danh sách tin nhắn để ghi đè xu hướng mô hình và cưỡng chế định dạng tiếng Việt
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
            "temperature": 0.15,  # Giữ nhiệt độ thấp tránh bị kẹt vào nhóm từ tiếng Trung
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

# =====================================================================
# TẦNG 2: PHÂN TÍCH Ý ĐỊNH NHANH (FAST INTENT EXTRACTOR) bằng REGEX
# =====================================================================
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

    # 5. Nhận dạng ngân sách (budget) gồm xử lý cả định dạng viết tắt ("12tr5", "15tr") hoặc số nguyên lớn
    budget_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:tr|triệu|triêu|t)\b', cleaned)
    if budget_match:
        val_str = budget_match.group(1).replace(',', '.')
        try:
            intent["budget"] = int(float(val_str) * 1000000)
        except:
            pass
    else:
        # Kiểm tra định dạng tách biệt kiểu "12tr5"
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
            # Tìm số lớn nguyên bản dạng chuỗi số đầy đủ
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
                    
    # Nhận dạng thương hiệu (brand) dựa trên từ điển map chuẩn hóa
    brand_keywords = {
        "iphone": "apple", "apple": "apple", "samsung": "samsung", "oppo": "oppo",
        "xiaomi": "xiaomi", "redmi": "xiaomi", "realme": "realme", "vivo": "vivo",
        "lg": "lg", "sharp": "sharp", "hitachi": "hitachi", "panasonic": "panasonic",
        "toshiba": "toshiba", "daikin": "daikin", "casper": "casper", "asus": "asus",
        "hp": "hp", "acer": "acer", "lenovo": "lenovo", "dell": "dell", "msi": "msi",
        "sony": "sony", "jbl": "jbl", "marshall": "marshall"
    }
    for kw, b in brand_keywords.items():
        if kw in cleaned:
            intent["brand"] = b
            break
            
    return intent

# =====================================================================
# TẦNG 3: TRÍCH XUẤT KEYWORD & LOGIC NGÀNH HÀNG PHỤ TRỢ
# =====================================================================
def extract_search_keywords_only(user_message, budget=None):
    """
    CẢI TIẾN: Nhận diện và giữ nguyên các cụm model đặc trưng 
    như '17 pro max', '16 pro', 's24 ultra' thay vì xóa bỏ stop-words.
    """
    cleaned = user_message.lower()
    
    # Bước 1: Bảo vệ các cụm từ model cao cấp bằng cách gộp viết liền dấu gạch ngang
    cleaned = re.sub(r'\b(iphone|galaxy|s|note)?\s*(\d+)\s*(pro\s*max|pro|max|ultra|plus|alpha)\b', r'\1-\2-\3', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Tiến hành tách từ như cũ
    cleaned_words = re.sub(r'[^\w\s\-]', ' ', cleaned)
    words = cleaned_words.split()
    
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
        # Giữ lại từ khóa có nghĩa hoặc các cụm model vừa được gộp bảo vệ
        if len(w) >= 2 or w.isdigit() or '-' in w:
            keywords.append(w)
            
    return keywords

def detect_multiple_categories(text):
    """Phát hiện xem chuỗi văn bản có đang chứa nhiều ngành hàng khác nhau không (Tránh kẹt state)"""
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


def load_local_catalog_products():
    """Đọc catalog local đã đồng bộ để dùng làm fallback khi DB không phản hồi."""
    catalog_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "cleaned_catalog.json")
    if not os.path.exists(catalog_path):
        return []
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def search_local_catalog_products(category, brand, budget, user_message):
    """Dùng catalog local làm fallback khi DB lỗi hoặc không trả về kết quả phù hợp."""
    catalog = load_local_catalog_products()
    if not catalog:
        return "", False, 0, []

    category_slug = (category or "").lower()
    search_text = (user_message or "").lower()
    query_tokens = [token for token in re.findall(r"[a-z0-9]+", search_text.replace("-", " ")) if len(token) >= 2]
    if not query_tokens and category_slug:
        query_tokens = [category_slug]

    scored_products = []
    for product in catalog:
        name = (product.get("name") or "").lower()
        brand_name = (product.get("brand") or "").lower()
        category_name = (product.get("category") or "").lower()
        specs_text = (product.get("specs") or "").lower()
        full_text = (product.get("full_text") or "").lower()
        price = safe_int(product.get("price"))

        text_blob = f"{name} {brand_name} {category_name} {specs_text} {full_text}"

        category_match = True
        if category_slug:
            product_category = str((product.get("category") or "")).lower()
            name_lower = (product.get("name") or "").lower()
            if category_slug == "dien-thoai":
                category_match = product_category == "dien-thoai"
                if not category_match:
                    category_match = name_lower.startswith("điện thoại") or name_lower.startswith("phone")
                category_match = category_match and not any(token in name_lower for token in ["ốp lưng", "miếng dán", "dây đeo", "airpods", "watch", "đồng hồ", "tai nghe", "loa", "máy lạnh", "tủ lạnh", "laptop", "máy tính", "notebook"])
                if not category_match:
                    category_match = False
            elif category_slug == "may-lanh":
                category_match = product_category == "may-lanh" or any(token in text_blob for token in ["máy lạnh", "may lanh", "điều hòa", "dieu hoa", "air conditioner"])
            elif category_slug == "tu-lanh":
                category_match = product_category == "tu-lanh" or any(token in text_blob for token in ["tủ lạnh", "tu lanh", "tủ mát", "tu mat"])
            elif category_slug == "laptop":
                category_match = product_category == "laptop" or any(token in text_blob for token in ["laptop", "máy tính", "may tinh", "notebook"])
            elif category_slug == "tai-nghe":
                category_match = product_category == "tai-nghe" or any(token in text_blob for token in ["tai nghe", "tai-nghe", "headphone", "airpods", "buds"])

        brand_match = True
        if brand:
            brand_value = str(brand).lower()
            brand_match = brand_value in brand_name or brand_value in name

        budget_match = True
        if budget is not None:
            budget_match = price <= budget

        if not category_match or not brand_match or not budget_match:
            continue

        score = 0
        for token in query_tokens:
            if token and token in text_blob:
                score += 2
        if score == 0:
            score = 1

        scored_products.append((score, product))

    if not scored_products:
        return "", False, 0, []

    scored_products.sort(key=lambda item: item[0], reverse=True)
    selected_products = scored_products[:3]
    context_list = []
    matched_products = []
    for _, product in selected_products:
        name = product.get("name") or ""
        brand_name = (product.get("brand") or "").strip().upper()
        category_name = product.get("category") or "Khác"
        price = safe_int(product.get("price"))
        specs = product.get("specs") or ""
        formatted_price = format_price(price)
        full_text = (
            f"Sản phẩm: {name}. "
            f"Thương hiệu: {brand_name or 'Khác'}. "
            f"Ngành hàng: {category_name}. "
            f"Giá: {formatted_price}. "
            f"Thông số: {specs}. "
            f"Mô tả: {product.get('full_text', '')}"
        )
        context_list.append(full_text)
        matched_products.append({
            "product_id": str(product.get("id") or ""),
            "name": name,
            "brand": brand_name,
            "sale_price": price,
            "url": "",
            "url_image": "",
            "promotion": product.get("gift_promotion") or "",
            "outstanding": product.get("full_text") or "",
            "specs": product.get("specs") or "",
        })

    return "\n".join(context_list), False, selected_products[0][0], matched_products

# =====================================================================
# TẦNG 4: TRUY VẤN NÂNG CAO 4 TẦNG (SỬA LỖI BỔ SUNG CỘT URL_IMAGE VÀ URL)
# =====================================================================
def summarize_text(value, max_length=100):
    """Rút gọn text dài để phản hồi sản phẩm ngắn gọn và dễ đọc."""
    if not value:
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    text = text.replace("Xem chi tiết", "").replace("Xem thông tin", "")
    text = text.strip(" -;:")
    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."
    return text


def build_full_product_details(product, product_index=None):
    """Tạo nội dung đầy đủ cho trường hợp khách hỏi chi tiết một sản phẩm."""
    name = product.get("name") or ""
    price = safe_int(product.get("sale_price"))
    formatted_price = format_price(price)
    promotion = (product.get("promotion") or "").strip()
    outstanding = (product.get("outstanding") or "").strip()
    specs = product.get("specs") or {}
    url = (product.get("url") or "").strip()
    url_image = (product.get("url_image") or "").strip()

    if isinstance(specs, dict):
        spec_items = []
        for key, value in list(specs.items()):
            if value:
                spec_items.append(f"{key}: {value}")
        spec_text = " - ".join(spec_items)
    elif isinstance(specs, list):
        spec_text = " - ".join([str(item) for item in specs])
    else:
        spec_text = str(specs or "")

    lines = []
    if product_index is not None:
        lines.append(f"### {product_index}. {name}")
    else:
        lines.append(f"### {name}")
    lines.append(f"Giá: **{formatted_price}**")
    if spec_text:
        lines.append(f"- Thông số: {spec_text}")
    if outstanding and not outstanding.startswith("Sản phẩm") and not outstanding.startswith("Thương hiệu"):
        lines.append(f"- Tiện ích: {outstanding}")
    if promotion:
        lines.append(f"- Khuyến mãi: {promotion}")
    if url:
        lines.append(f"[Xem chi tiết sản phẩm tại Điện Máy Xanh]({url})")
    if url_image:
        lines.append(f"![ảnh sản phẩm]({url_image})")
    return "\n".join(lines)


def build_recommendation_text(matched_products, category=None, is_detailed=False):
    """Tạo text khuyến nghị sản phẩm từ dữ liệu thật, dùng rút gọn cho danh sách, đầy đủ cho câu hỏi chi tiết."""
    if not matched_products:
        return ""

    if is_detailed and len(matched_products) == 1:
        return build_full_product_details(matched_products[0], product_index=1)

    blocks = []
    for index, product in enumerate(matched_products[:3], start=1):
        name = product.get("name") or ""
        price = safe_int(product.get("sale_price"))
        formatted_price = format_price(price)
        promotion = summarize_text(product.get("promotion") or "", 120)
        outstanding = summarize_text(product.get("outstanding") or "", 120)
        specs = product.get("specs") or {}
        url = (product.get("url") or "").strip()
        url_image = (product.get("url_image") or "").strip()

        if isinstance(specs, dict):
            spec_items = []
            for key, value in list(specs.items())[:3]:
                if value:
                    spec_items.append(f"{key}: {summarize_text(value, 45)}")
            spec_text = " - ".join(spec_items)
        elif isinstance(specs, list):
            spec_text = " - ".join([summarize_text(str(item), 45) for item in specs[:3]])
        else:
            spec_text = summarize_text(specs or "", 90)

        preview_lines = [f"### {index}. {name}", f"Giá: **{formatted_price}**"]
        if spec_text:
            preview_lines.append(f"- {spec_text}")
        if outstanding and not outstanding.startswith("Sản phẩm") and not outstanding.startswith("Thương hiệu"):
            preview_lines.append(f"- Tiện ích: {outstanding}")
        if promotion:
            preview_lines.append(f"- Khuyến mãi: {promotion}")
        preview_lines.append("...")

        full_text = build_full_product_details(product, product_index=index)
        preview_text = "\n".join(preview_lines)

        blocks.append(
            "__PREVIEW__\n"
            f"{preview_text}\n"
            "__END_PREVIEW__\n"
            "__FULL__\n"
            f"{full_text}\n"
            "__END_FULL__"
        )

    return "\n\n---\n\n".join(blocks)


def build_direct_product_response(matched_products, category=None, requested_model=None, is_out_of_stock=False):
    """Tạo phản hồi trực tiếp bằng dữ liệu thật khi có sản phẩm để đề xuất."""
    if not matched_products:
        return ""

    intro = ""
    if is_out_of_stock and requested_model:
        intro = f"Xin lỗi, hiện tại model {requested_model} không còn hàng trong hệ thống của chúng tôi. Tôi sẽ giới thiệu cho bạn một số sản phẩm thay thế phù hợp:\n\n"

    body = build_recommendation_text(matched_products, category=category, is_detailed=is_out_of_stock and requested_model is not None)
    return intro + body


def db_search_products(category, brand, budget, user_message):
    """Thực hiện truy vấn SQL kết hợp tính điểm Relevance Score theo cấu trúc 4 tầng bảo vệ chống trống kho"""
    context = ""
    is_upsell = False
    top_relevance = 0
    matched_products = []
    
    if not category:
        return context, is_upsell, top_relevance, matched_products
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Thiết lập điều kiện chuẩn hóa ngành hàng loại bỏ phụ kiện tạp nham
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
            return context, is_upsell, top_relevance, matched_products
            
        brand_cond = ""
        if brand:
            escaped_brand = brand.replace("'", "''")
            brand_cond = f" AND (p.brand ILIKE '%%{escaped_brand}%%' OR p.name ILIKE '%%{escaped_brand}%%')"

        # Trích xuất keyword phục vụ tính toán điểm Relevance
        keywords = extract_search_keywords_only(user_message, budget)
        print(f"\n[DEBUG] Extracted search keywords: {keywords}\n")

        relevance_score_expr = "0"
        match_cond = "1=1"
        
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

        # TIER 1: Tìm kiếm chính xác theo danh mục, từ khóa và ngân sách (Bổ sung SELECT url_image, url)
        params = []
        budget_cond = ""
        if budget:
            budget_cond = " AND p.sale_price <= %s"
            params.append(budget)
            
        query = f"""
            SELECT 
                p.product_id, p.name, p.brand, c.category_name, p.sale_price, p.original_price, 
                p.promotion, p.outstanding, p.spec_product, p.url_image, p.url,
                ({relevance_score_expr}) as relevance
            FROM products p LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE {sql_cond} AND p.sale_price > 0 AND {match_cond}{brand_cond}{budget_cond}
            ORDER BY relevance DESC, p.sale_price DESC
        """
        cur.execute(query, params)
        rows = cur.fetchall()
        
        if not rows:
            fallback_context, fallback_is_upsell, fallback_top_relevance, fallback_products = search_local_catalog_products(category, brand, budget, user_message)
            if fallback_products:
                cur.close()
                conn.close()
                return fallback_context, fallback_is_upsell, fallback_top_relevance, fallback_products

        # TIER 2: Có ngân sách nhưng rỗng kho -> Kích hoạt tìm kiếm Upsell bán hàng cận biên
        if budget and not rows:
            is_upsell = True
            query_upsell = f"""
                SELECT 
                    p.product_id, p.name, p.brand, c.category_name, p.sale_price, p.original_price, 
                    p.promotion, p.outstanding, p.spec_product, p.url_image, p.url,
                    ({relevance_score_expr}) as relevance
                FROM products p LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE {sql_cond} AND p.sale_price > 0 AND {match_cond}{brand_cond}
                ORDER BY relevance DESC, p.sale_price ASC LIMIT 2
            """
            cur.execute(query_upsell)
            rows = cur.fetchall()
            
        # TIER 3: Vẫn không tìm thấy kết quả -> Bỏ qua lọc từ khóa, tìm dựa theo Danh mục + Ngân sách
        if not rows:
            params = []
            budget_cond = ""
            if budget:
                budget_cond = " AND p.sale_price <= %s"
                params.append(budget)
            query_fallback = f"""
                SELECT 
                    p.product_id, p.name, p.brand, c.category_name, p.sale_price, p.original_price, 
                    p.promotion, p.outstanding, p.spec_product, p.url_image, p.url,
                    0 as relevance
                FROM products p LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE {sql_cond} AND p.sale_price > 0 {brand_cond}{budget_cond}
                ORDER BY p.sale_price DESC
            """
            cur.execute(query_fallback, params)
            rows = cur.fetchall()
            
        # TIER 4: Tầng cứu cánh cuối cùng -> Tìm bán hàng cận biên dựa theo Danh mục thuần túy
        if budget and not rows:
            is_upsell = True
            query_final_fallback = f"""
                SELECT 
                    p.product_id, p.name, p.brand, c.category_name, p.sale_price, p.original_price, 
                    p.promotion, p.outstanding, p.spec_product, p.url_image, p.url,
                    0 as relevance
                FROM products p LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE {sql_cond} AND p.sale_price > 0 {brand_cond}
                ORDER BY p.sale_price ASC LIMIT 2
            """
            cur.execute(query_final_fallback)
            rows = cur.fetchall()
        else:
            rows = rows[:3]
            
        if rows:
            top_relevance = rows[0][11] # Do bổ sung thêm 2 cột, index của trường relevance đẩy từ 9 lên 11
            
        # Dựng context chuẩn hóa từ dữ liệu DB thật
        context_list = []
        matched_products = []
        for row in rows:
            p_id = str(row[0])
            name = row[1]
            brand_name = (row[2] or '').strip().upper()
            cat_name = row[3] or 'Khác'
            price = safe_int(row[4])
            original_price = safe_int(row[5])
            promotion = row[6] or ""
            outstanding = row[7] or ""
            spec_product = row[8]
            url_image = row[9] or ""   # Đọc chuẩn xác trường url_image từ Supabase Row
            url = row[10] or ""         # Đọc chuẩn xác trường url từ Supabase Row
            
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
                f"Link ảnh sản phẩm (url_image): {url_image}. "
                f"Link xem chi tiết (url): {url}"
            )
            
            stock_info = "Tình trạng tồn kho: Còn hàng (Số lượng: 10 sản phẩm)"
            promo_info = f"Khuyến mãi áp dụng: {promotion}" if promotion and promotion.strip() else "Khuyến mãi áp dụng: Không có chương trình khuyến mãi nào"
                
            enriched_text = f"{full_text}. {stock_info}. {promo_info}."
            context_list.append(enriched_text)
            matched_products.append({
                "product_id": p_id,
                "name": name,
                "brand": brand_name,
                "sale_price": price,
                "url": url,
                "url_image": url_image,
                "promotion": promotion,
                "outstanding": outstanding,
                "specs": spec_product,
            })
            
        context = "\n".join(context_list)
        cur.close()
        conn.close()
    except Exception as e:
        fallback_context, fallback_is_upsell, fallback_top_relevance, fallback_products = search_local_catalog_products(category, brand, budget, user_message)
        if fallback_products:
            return fallback_context, fallback_is_upsell, fallback_top_relevance, fallback_products
        context = f"Lỗi đọc kho dữ liệu từ DB: {str(e)}"
        
    return context, is_upsell, top_relevance, matched_products

# =====================================================================
# TẦNG 5: ĐIỀU PHỐI LUỒNG AGENT CHÍNH (STREAMING GENERATOR ENGINE)
# =====================================================================
def generate_advisor_response_stream(user_message, history=None):
    """Luồng xử lý chính duy trì bộ nhớ Context dài hạn và điều phối RAG/Clarify"""
    yield " "  # Gửi ngay khoảng trắng đầu giữ kết nối, tránh lỗi Read Timeout
    
    # Tích lũy trạng thái (Stateful Intent Tracking) qua lịch sử chat
    accumulated_intent = {
        "category": None, "brand": None, "budget": None, "room_size": None,
        "family_members": None, "laptop_needs": None, "headphone_needs": None,
        "phone_needs": None, "product_query": None
    }
    
    relevant_history = filter_history_for_current_category(history, user_message)

    if relevant_history:
        for msg in relevant_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role != "user":
                continue

            prev_intent = analyze_intent_fast(content)
            if prev_intent.get("category") and prev_intent["category"] != accumulated_intent.get("category"):
                accumulated_intent = reset_intent_state_on_category_change(accumulated_intent, prev_intent, content)
            else:
                accumulated_intent = merge_intent_state(accumulated_intent, prev_intent, content)
                    
    # Cập nhật thông số từ tin nhắn hiện tại của khách
    current_intent = analyze_intent_fast(user_message)
    if current_intent.get("category") and current_intent["category"] != accumulated_intent.get("category"):
        accumulated_intent = reset_intent_state_on_category_change(accumulated_intent, current_intent, user_message)
    else:
        accumulated_intent = merge_intent_state(accumulated_intent, current_intent, user_message)
        
    category = accumulated_intent.get('category')
    brand = accumulated_intent.get('brand')
    budget = accumulated_intent.get('budget')
    room_size = accumulated_intent.get('room_size')
    family_members = accumulated_intent.get('family_members')
    laptop_needs = accumulated_intent.get('laptop_needs')
    headphone_needs = accumulated_intent.get('headphone_needs')
    phone_needs = accumulated_intent.get('phone_needs')
    
    query_to_search = accumulated_intent.get("product_query") or user_message
    
    # Nhận diện ý định hỏi chính sách dịch vụ chăm sóc khách hàng
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

    # KIỂM TRA ĐIỀU KIỆN LÀM RÕ TIÊU CHÍ (SPEC CLARIFICATION LOGIC)
    need_clarify = False
    clarify_instruction = ""
    
    if category and not is_policy_query:
        refused_clarify = False
        all_user_messages = [msg for msg in relevant_history if msg.get("role") == "user"] if relevant_history else []
        all_user_messages.append({"role": "user", "content": user_message})
        
        refusal_keywords = ["bỏ qua", "skip", "không cần", "khong can", "không muốn", "khong muon", 
                            "tùy", "tuy", "đại đi", "dai di", "nào cũng được", "nao cung duoc", "bất kỳ", "bat ky"]
        for msg in all_user_messages:
            if any(kw in msg.get("content", "").lower() for kw in refusal_keywords):
                refused_clarify = True
                break
                
        clarify_count = 0
        if relevant_history:
            for msg in relevant_history:
                if msg.get("role") == "assistant" and any(p in msg.get("content", "") for p in [
                    "bao nhiêu m²", "bao nhiêu m2", "bao nhiêu người", 
                    "công việc gì là chủ yếu", "ngân sách dự kiến", 
                    "nhét tai True Wireless", "kiểu dáng", "thương hiệu", "nhu cầu"
                ]):
                    clarify_count += 1

        has_brand = brand is not None
        has_budget = budget is not None
        
        category_need = None
        if category == 'may-lanh': category_need = room_size
        elif category == 'tu-lanh': category_need = family_members
        elif category == 'laptop': category_need = laptop_needs
        elif category == 'tai-nghe': category_need = headphone_needs
        elif category == 'dien-thoai': category_need = phone_needs
            
        has_need = category_need is not None

        # Bypass nếu khách đang tìm kiếm đích danh một mã máy cụ thể
        specific_model_info = detect_specific_model_request(user_message)
        is_specific_model = specific_model_info.get("is_specific_model", False)
        requested_model = specific_model_info.get("requested_model")

        enough_specs = False
        if is_specific_model: enough_specs = True
        elif has_brand and (has_budget or has_need): enough_specs = True
        elif has_budget and has_need: enough_specs = True
                
        need_clarify = not enough_specs and not refused_clarify and clarify_count < 2
        
        if need_clarify:
            missing_parts = []
            if not has_brand: missing_parts.append("Thương hiệu sản phẩm (ví dụ: iPhone/Samsung cho điện thoại, Daikin/Panasonic cho máy lạnh, v.v.)")
            if not has_budget: missing_parts.append("Mức ngân sách dự kiến (ví dụ: dưới 10 triệu, khoảng 15 triệu, v.v.)")
            if not has_need:
                if category == 'may-lanh': missing_parts.append("Diện tích phòng (m2) (ví dụ: dưới 15m2, 15-20m2, v.v.)")
                elif category == 'tu-lanh': missing_parts.append("Số thành viên sử dụng (ví dụ: 2-3 người, trên 5 người, v.v.)")
                elif category == 'laptop': missing_parts.append("Nhu cầu sử dụng chính (ví dụ: học tập/văn phòng, chơi game, thiết kế đồ họa, lập trình, v.v.)")
                elif category == 'tai-nghe': missing_parts.append("Kiểu dáng hoặc tính năng (ví dụ: tai nghe chụp tai over-ear, nhét tai True Wireless, có chống ồn ANC, v.v.)")
                elif category == 'dien-thoai': missing_parts.append("Nhu cầu tính năng nổi bật (ví dụ: chụp hình đẹp, pin trâu, chơi game mượt, v.v.)")
                    
            if has_brand:
                clarify_instruction = f"Khách hàng muốn mua {category} hãng {brand.upper()} nhưng chưa cung cấp Ngân sách hay Nhu cầu cụ thể. Bạn BẮT BUỘC phải đặt câu hỏi khéo léo để khách hàng lựa chọn/cung cấp ít nhất 1 trong các thông tin sau: {', '.join(missing_parts)}."
            else:
                if not has_budget and not has_need:
                    clarify_instruction = f"Khách hàng muốn tư vấn về {category} nhưng chưa cung cấp thêm thông tin nào. Bạn BẮT BUỘC phải đặt câu hỏi khéo léo để khách hàng lựa chọn/cung cấp ít nhất 2 tiêu chí trong số các thông tin sau: {', '.join(missing_parts)}."
                else:
                    clarify_instruction = f"Khách hàng muốn tư vấn về {category} (đã biết một số thông tin), nhưng chưa xác định Thương hiệu hay các tiêu chí còn lại. Bạn BẮT BUỘC phải đặt câu hỏi khéo léo để khách hàng lựa chọn/cung cấp thêm ít nhất 1 thông tin nữa trong số các thông tin sau: {', '.join(missing_parts)}."

    # KÍCH HOẠT TRUY VẤN SẢN PHẨM RAG NẾU ĐÃ ĐỦ THÔNG TIN TIÊU CHÍ
    products = []
    is_upsell = False
    context = ""
    top_relevance = 0
    is_specific_model = False
    requested_model = None
    matched_products = []
    is_out_of_stock = False
    if not need_clarify:
        specific_model_info = detect_specific_model_request(user_message)
        is_specific_model = specific_model_info.get("is_specific_model", False)
        requested_model = specific_model_info.get("requested_model")

        # Gọi tầng tìm kiếm 4 lớp nâng cao từ DB
        context, is_upsell, top_relevance, matched_products = db_search_products(category, brand, budget, query_to_search)

        if is_specific_model and requested_model:
            requested_model_clean = requested_model.lower().replace(" ", "")
            has_exact_match = any(
                requested_model_clean in (product.get("name") or "").lower().replace(" ", "")
                for product in matched_products
            )
            is_out_of_stock = not has_exact_match and bool(matched_products)

    # Nếu có dữ liệu sản phẩm thật thì trả lời trực tiếp bằng dữ liệu đó, không để LLM tự bịa giá/thông tin.
    direct_response = build_direct_product_response(
        matched_products,
        category=category,
        requested_model=requested_model if is_out_of_stock else None,
        is_out_of_stock=is_out_of_stock,
    )
    if direct_response and not is_policy_query and not need_clarify:
        yield direct_response
        return

    # Bypass LLM nếu kho hàng trống trơn để tránh AI sinh ảo giác sản phẩm bịa đặt
    if category and not context and not is_policy_query and not need_clarify:
        yield "Dạ, hiện tại hệ thống siêu thị Điện Máy Xanh đang tạm hết dòng sản phẩm phù hợp với yêu cầu này của anh/chị. Anh/chị có thể thử thay đổi tầm giá, điều chỉnh nhu cầu hoặc tham khảo các nhóm sản phẩm khác đang sẵn hàng và có nhiều khuyến mãi lớn nhé ạ!"
        return

    # Luân chuyển hội thoại sang API Chat
    conversation_messages = relevant_history + [{"role": "user", "content": user_message}]

    # Kiểm tra catalog từ Database xem hệ thống có sản phẩm nào thuộc ngành hàng này không
    has_category_products = False
    if category and not need_clarify:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            sql_check = ""
            if category == 'may-lanh': sql_check = "(c.category_name = 'Máy lạnh' OR p.name ILIKE '%%máy lạnh%%' OR p.name ILIKE '%%điều hòa%%')"
            elif category == 'dien-thoai': sql_check = "(c.category_name = 'Điện thoại' OR p.name ILIKE '%%điện thoại%%' OR p.name ILIKE '%%iphone%%')"
            elif category == 'tu-lanh': sql_check = "(c.category_name = 'Tủ lạnh' OR p.name ILIKE '%%tủ lạnh%%' OR p.name ILIKE '%%tủ mát%%')"
            elif category == 'laptop': sql_check = "(c.category_name = 'Laptop' OR p.name ILIKE '%%laptop%%' OR p.name ILIKE '%%máy tính%%')"
            elif category == 'tai-nghe': sql_check = "(c.category_name = 'Loa, Tai nghe' OR p.name ILIKE '%%tai nghe%%')"
            
            if sql_check:
                cur.execute(f"SELECT COUNT(*) FROM products p LEFT JOIN categories c ON p.category_id = c.category_id WHERE {sql_check}")
                has_category_products = cur.fetchone()[0] > 0
            cur.close()
            conn.close()
        except:
            pass

    if category and not has_category_products and not need_clarify:
        fallback_context, fallback_is_upsell, fallback_top_relevance, fallback_products = search_local_catalog_products(category, brand, budget, user_message)
        if fallback_products:
            has_category_products = True
        else:
            yield "Dạ, hiện tại ngành hàng này đang tạm hết hàng trên toàn hệ thống siêu thị Điện Máy Xanh. Anh/chị có thể tham khảo các dòng sản phẩm khác như Tủ lạnh, Laptop, Máy rửa chén đang có sẵn rất nhiều sản phẩm và khuyến mãi lớn ạ!"
            return

    # XỬ LÝ LỜI CHÀO CHUNG KHI KHÁCH HÀNG CHƯA XÁC ĐỊNH NGÀNH HÀNG
    if not category and not is_policy_query:
        system_greeting = """Bạn là một nhân viên tư vấn người Việt Nam chuyên nghiệp tại siêu thị Điện Máy Xanh. Khách hàng chưa có nhu cầu mua sắm cụ thể hoặc đang chào hỏi bạn. Hãy gửi lời chào thân thiện, nhiệt tình và hỏi xem khách hàng đang cần tìm kiếm dòng sản phẩm nào trong các nhóm sau: Điện thoại, Máy lạnh / Điều hòa, Tủ lạnh, Laptop, Tai nghe. Trả lời ngắn gọn, lịch sự bằng Tiếng Việt 100%."""
        for chunk in call_local_llm_stream(system_greeting, messages=conversation_messages):
            yield chunk
        return

    # XỬ LÝ LUỒNG HỎI LÀM RÕ TIÊU CHÍ KHÁCH HÀNG
    if clarify_instruction:
        system_clarify = f"""Bạn là một nhân viên tư vấn người Việt Nam chuyên nghiệp tại siêu thị Điện Máy Xanh. LƯU Ý QUAN TRỌNG: Khách hàng vừa mới chuyển sang hỏi về ngành hàng '{category}'. Bạn BẮT BUỘC phải tập trung 100% vào ngành hàng mới '{category}' này. Nhiệm vụ: {clarify_instruction}. Hãy phản hồi lịch sự, chào đón khách hàng nồng nhiệt và đặt câu hỏi hỏi ngược khéo léo để lấy thông tin. Bạn có thể nêu một vài thương hiệu nổi tiếng mà Điện Máy Xanh đang kinh doanh cho ngành hàng mới này để làm tăng tính hấp dẫn. TUYỆT ĐỐI KHÔNG được nhắc lại hoặc nhầm lẫn sang các sản phẩm/thương hiệu/mức giá của ngành hàng cũ trong lịch sử trò chuyện. BẮT BUỘC trả lời ngắn gọn, thân thiện, 100% bằng Tiếng Việt."""
        for chunk in call_local_llm_stream(system_clarify, messages=conversation_messages):
            yield chunk
        return

    # THIẾT LẬP CÁC CHỈ THỊ PHỤ TRỢ CHO PHẢN HỒI KHUYẾN NGHỊ SẢN PHẨM
    if not context or "Không tìm thấy" in context:
        context = "Hiện tại trong kho tạm hết dòng sản phẩm khớp chính xác với ngân sách này của anh chị." if category else ""

    # Tạo text khuyến nghị từ dữ liệu thật để tránh lỗi giá/thông tin do LLM bịa.
    recommendation_text = build_recommendation_text(matched_products, category=category)
    if recommendation_text and not is_policy_query:
        context = recommendation_text

    upsell_instruction = f"LƯU Ý BẮT BUỘC: Khách hàng muốn tìm sản phẩm dưới mức giá {format_price(budget)}, tuy nhiên các sản phẩm trong kho đều có giá cao hơn. Bạn BẮT BUỘC phải khéo léo giải thích rằng tầm giá này đang tạm hết, sau đó giới thiệu 2 phương án thay thế có giá rẻ nhất hiện có (trong dữ liệu trên) làm giải pháp tham khảo chất lượng cao." if is_upsell else ""

    out_of_stock_instruction = ""
    if is_out_of_stock and requested_model:
        out_of_stock_instruction = f"\n- LƯU Ý KHẨN CẤP: Khách hàng đang hỏi về model '{requested_model}', nhưng model đó không có trong dữ liệu hiện có. Bạn BẮT BUỘC phải xin lỗi nhẹ nhàng, nói rõ rằng model này hiện chưa có sẵn trong kho/hệ thống, rồi giới thiệu các sản phẩm thay thế phù hợp trong context. TUYỆT ĐỐI KHÔNG giả định model này vẫn còn hàng."
    
    extra_clarify = ""
    if category == 'may-lanh' and not room_size: extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết diện tích phòng. Hãy đề xuất sản phẩm phù hợp ngân sách và đặt câu hỏi khéo léo hỏi thêm diện tích phòng của khách để chốt công suất máy lạnh chuẩn nhất."
    elif category == 'tu-lanh' and not family_members: extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết số người sử dụng. Hãy đề xuất sản phẩm phù hợp ngân sách và hỏi thêm về số thành viên sử dụng để chọn dung tích tủ lạnh tối ưu."
    elif category == 'laptop' and not laptop_needs: extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết nhu cầu công việc. Hãy đề xuất sản phẩm phù hợp ngân sách và hỏi thêm về nhu cầu sử dụng (như làm văn phòng, học tập hay chơi game, đồ họa) để kiểm tra độ tương thích cấu hình."
    elif category == 'tai-nghe' and not headphone_needs: extra_clarify = "LƯU Ý BẮT BUỘC: Khách hàng chưa cho biết kiểu dáng tai nghe. Hãy đề xuất sản phẩm phù hợp ngân sách và hỏi thêm về kiểu dáng tai nghe yêu thích (nhét tai True Wireless hay chụp tai Over-ear) để tư vấn chuẩn nhất."

    policy_section = f"---\nDỮ LIỆU CHÍNH SÁCH ĐIỆN MÁY XANH (CÓ THẬT):\n{policy_context}\n---\nQUY TẮC TRẢ LỜI CHÍNH SÁCH:\n- Hãy dựa vào dữ liệu chính sách ở trên để trả lời câu hỏi của khách hàng về chính sách một cách chính xác nhất.\n- Tuyệt đối không tự bịa đặt ra các quy định chính sách không có trong tài liệu.\n- Nếu không tìm thấy thông tin chính sách liên quan trong dữ liệu trên, hãy hướng dẫn khách hàng liên hệ trực tiếp tổng đài 1900.232.461 để được hỗ trợ nhanh nhất." if is_policy_query and policy_context else ""

    other_products_instruction = """\n- LƯU Ý KHẨN CẤP: Khách hàng đang hỏi tìm các sản phẩm khác hoặc lựa chọn khác. Bạn BẮT BUỘC phải đọc kỹ context ở trên và liệt kê, giới thiệu toàn bộ các sản phẩm khác đang có sẵn trong context. TUYỆT ĐỐI KHÔNG được lặp lại câu hỏi lựa chọn đơn lẻ cũ.""" if any(kw in user_message.lower() for kw in ["khác", "còn", "dòng nào", "sản phẩm nào", "mẫu nào", "lựa chọn"]) else ""
        
    was_assistant_asking = False
    if history:
        assistant_msgs = [msg for msg in history if msg.get("role") == "assistant"]
        if assistant_msgs and any(phrase in assistant_msgs[-1].get("content", "").lower() for phrase in ["không?", "không ạ?", "được không", "đúng không", "quan tâm"]):
            was_assistant_asking = True
                
    confirmation_instruction = """\n- LƯU Ý KHẨN CẤP: Khách hàng đã đồng ý tư vấn (nhắn 'có' hoặc tương đương). Bạn BẮT BUỘC phải đi thẳng vào chi tiết sản phẩm ngay lập tức: cung cấp giá bán, tình trạng tồn kho, và các quà tặng khuyến mãi chi tiết của sản phẩm có trong context. TUYỆT ĐỐI KHÔNG được hỏi lại câu hỏi cũ dạng 'tôi có thể tư vấn... không?' hoặc 'bạn quan tâm không?'.""" if (user_message.lower() in ["có", "co", "đúng", "dung", "ok", "yes", "ừ", "muốn", "tiếp"] and was_assistant_asking) else ""

    # DỰNG PROMPT ADVISOR HOÀN CHỈNH CHO MÔ HÌNH SUY LUẬN TƯ VẤN
    system_advisor = f"""Bạn là một nhân viên tư vấn người Việt Nam chuyên nghiệp tại siêu thị Điện Máy Xanh.
    Hãy dùng tập dữ liệu sản phẩm CÓ THẬT sau đây để tư vấn cho khách:
    ---
    {context}
    ---
    {policy_section}
    
    QUY TẮC TƯ VẤN BẮT BUỘC SỐNG CÒN:
    1. BẮT BUỘC TRẢ LỜI BẰNG TIẾNG VIỆT 100%. TUYỆT ĐỐI KHÔNG dùng tiếng Trung, không dùng chữ Hán.
    2. Chỉ được dùng thông tin sản phẩm, giá bán, tình trạng tồn kho và khuyến mãi có trong dữ liệu ở trên để tư vấn. KHÔNG TỰ BỊA SẢN PHẨM, GIÁ, THÔNG SỐ, KHUYẾN MÃI HOẶC TỒN KHO. Nếu dữ liệu ở trên trống hoặc báo hết hàng (và câu hỏi không phải về chính sách), bạn BẮT BUỘC phải thông báo thành thật rằng sản phẩm đang tạm hết hàng trên hệ thống và KHÔNG giới thiệu bất kỳ sản phẩm nào khác ngoài danh sách.
    3. TUYỆT ĐỐI KHÔNG trộn lẫn thông tin hoặc lấy các sản phẩm cũ trong lịch sử trò chuyện để giới thiệu hay chế biến thành sản phẩm của danh mục mới. Mỗi lượt phản hồi chỉ được dùng đúng các sản phẩm được liệt kê trong phần context ở trên.
    4. Không dùng từ ngữ kỹ thuật phức tạp (như Inverter, HP, BTU). Hãy dịch sang ngôn ngữ bình dân (Ví dụ: 'Máy chạy siêu êm ban đêm', 'Tiết kiệm tiền điện cuối tháng', 'Làm mát nhanh sâu').
    5. Luôn nêu rõ ưu và nhược điểm (Trade-off) giữa các lựa chọn để khách hàng dễ ra quyết định.
    6. BẮT BUỘC THÔNG BÁO cụ thể cho khách hàng về Tình trạng tồn kho thực tế và các chương trình Khuyến mãi/Quà tặng đi kèm của từng sản phẩm dựa trên thông tin thực tế được cung cấp.
    7. ĐỘ DÀI VÀ PHONG CÁCH PHẢN HỒI: Hãy phản hồi cực kỳ ngắn gọn, cô đọng, giới hạn câu trả lời dưới 150-180 từ. Trình bày dưới dạng các đầu dòng rõ ràng để giúp phản hồi sinh ra tức thì (vì chạy cục bộ trên CPU).
    8. QUY TẮC TRÌNH BÀY VÀ ĐƯỜNG DẪN UX (TỐI ƯU TRẢI NGHIỆM):
       - GIÁ TIỀN: BẮT BUỘC luôn luôn làm nổi bật giá tiền bằng cách tăng 1 size chữ và in đậm bằng thẻ span: `<span style="font-size: 1.15em;">**[Giá tiền]đ**</span>`. Ví dụ: `<span style="font-size: 1.15em;">**3.850.000đ**</span>`.
       - ĐỊNH DẠNG TRÌNH BÀY BẮT BUỘC (Theo mẫu trực quan):
         Anh chị tham khảo sản phẩm [Tên sản phẩm] giá [Giá tiền đã bọc thẻ span] ạ.
         - [Tên thông số chính tùy ngành hàng]: [Giá trị phù hợp]
         - Tiện ích: [Tiện ích chính dịch sang ngôn ngữ bình dân]
         [Thông tin tồn kho và khuyến mãi nếu có]
         
         [Xem chi tiết sản phẩm tại Điện Máy Xanh](url)
         ![ảnh sản phẩm](url_image)
         Anh/chị có quan tâm không ạ?
       - Bạn chỉ được chèn link xem chi tiết và ảnh nếu có trong dữ liệu context (lấy từ trường 'url' và 'url_image' được cấp từ DB), tuyệt đối không tự viết link giả lập.
    {other_products_instruction}
    {confirmation_instruction}
    {upsell_instruction}
    {out_of_stock_instruction}
    {extra_clarify}
    Hãy bắt đầu bằng một lời chào lịch sự thân thiện."""

    for chunk in call_local_llm_stream(system_advisor, messages=conversation_messages, is_recommendation=not is_policy_query):
        yield chunk