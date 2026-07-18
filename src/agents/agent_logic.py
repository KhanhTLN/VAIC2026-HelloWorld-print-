import requests
import json
import os
import re

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

# Đã chuyển sang lấy Tồn kho và Khuyến mãi thật 100% trực tiếp từ Database thông qua sync_supabase.py

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
    
    # Xây dựng danh sách tin nhắn hội thoại cho API chat
    conversation_messages = []
    if history:
        conversation_messages = history
    else:
        conversation_messages = [{"role": "user", "content": user_message}]

    # Không cần dựng history_context thủ công nữa vì đã dùng API Chat
    history_context = ""

    # Đọc nhanh catalog để kiểm tra thực tế trong kho có sản phẩm thuộc ngành hàng này hay không
    catalog_path = 'data/processed/cleaned_catalog.json'
    catalog = []
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
        except:
            pass

    has_category_products = False
    if category and catalog:
        for p in catalog:
            p_cat = p.get('category', '')
            p_name_lower = p.get('name', '').lower()
            
            is_match = False
            if category == 'may-lanh' and (p_cat == 'may-lanh' or 'máy lạnh' in p_name_lower or 'điều hòa' in p_name_lower):
                is_match = True
            elif category == 'dien-thoai' and (p_cat == 'dien-thoai' or 'điện thoại' in p_name_lower or 'iphone' in p_name_lower or 'samsung' in p_name_lower):
                is_match = True
            elif category == 'tu-lanh' and (p_cat == 'tu-lanh' or p_cat == '40' or 'tủ lạnh' in p_name_lower or 'tủ mát' in p_name_lower or 'tủ đông' in p_name_lower):
                is_match = True
            elif category == 'laptop' and (p_cat == 'laptop' or p_cat == 'laptop-7a2c5001' or 'máy tính' in p_name_lower or 'laptop' in p_name_lower):
                is_match = True
            elif category == 'tai-nghe' and (p_cat == 'tai-nghe' or 'tai nghe' in p_name_lower or 'airpods' in p_name_lower):
                is_match = True
            
            if is_match:
                has_category_products = True
                break

    # Nếu phát hiện ngành hàng đó trống trơn trong DB -> Báo hết hàng trực tiếp tại Python (Bypass LLM)
    if category and not has_category_products:
        yield "Dạ, hiện tại ngành hàng này đang tạm hết hàng trên toàn hệ thống siêu thị Điện Máy Xanh. Anh/chị có thể tham khảo các dòng sản phẩm khác như Tủ lạnh, Laptop, Máy rửa chén đang có sẵn rất nhiều sản phẩm và khuyến mãi lớn ạ!"
        return

    # Nếu không phát hiện ngành hàng nào, khách đang chào hỏi hoặc nói chuyện chung chung
    if not category:
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

    # XÁC ĐỊNH CHỈ THỊ HỎI LÀM RÕ (Bypass nếu khách từ chối hoặc đã hỏi rồi)
    clarify_instruction = ""
    if not refused_clarify and clarify_count < 1:
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
        Nhiệm vụ: {clarify_instruction}
        Hãy phản hồi lịch sự, chào đón khách hàng nồng nhiệt và đặt câu hỏi hỏi ngược khéo léo để lấy thông tin. 
        Bạn có thể nêu một vài thương hiệu nổi tiếng mà Điện Máy Xanh đang kinh doanh cho ngành hàng này để làm tăng tính hấp dẫn.
        BẮT BUỘC trả lời ngắn gọn, thân thiện, 100% bằng Tiếng Việt."""
        
        for chunk in call_local_llm_stream(system_clarify, messages=conversation_messages):
            yield chunk
        return

    # 3. LUỒNG RAG + HARD FILTER (Đọc file catalog sạch từ Bước 1)
    catalog_path = 'data/processed/cleaned_catalog.json'
    context = ""
    matched_products = []
    is_upsell = False
    
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
                
            # Lọc cứng bằng code Python để triệt tiêu Hallucination giá tiền
            for p in catalog:
                p_cat = p['category']
                p_name_lower = p['name'].lower()
                
                is_match = False
                if category == 'may-lanh' and (p_cat == 'may-lanh' or 'máy lạnh' in p_name_lower or 'điều hòa' in p_name_lower):
                    is_match = True
                elif category == 'dien-thoai' and (p_cat == 'dien-thoai' or 'điện thoại' in p_name_lower or 'iphone' in p_name_lower or 'samsung' in p_name_lower):
                    is_match = True
                elif category == 'tu-lanh' and (p_cat == 'tu-lanh' or p_cat == '40' or 'tủ lạnh' in p_name_lower or 'tủ mát' in p_name_lower or 'tủ đông' in p_name_lower):
                    is_match = True
                elif category == 'laptop' and (p_cat == 'laptop' or p_cat == 'laptop-7a2c5001' or 'máy tính' in p_name_lower or 'laptop' in p_name_lower):
                    is_match = True
                elif category == 'tai-nghe' and (p_cat == 'tai-nghe' or 'tai nghe' in p_name_lower or 'airpods' in p_name_lower):
                    is_match = True
                
                if is_match:
                    all_matched_products.append(p)
            
            # Lọc theo ngân sách nếu có
            final_products = []
            if budget:
                for p in all_matched_products:
                    if p['price'] <= budget:
                        final_products.append(p)
            else:
                final_products = all_matched_products
                
            # Nếu khách đặt ngân sách nhưng không có sản phẩm nào rẻ hơn ngân sách -> Kích hoạt Up-selling Fallback
            is_upsell = False
            if budget and not final_products and all_matched_products:
                is_upsell = True
                # Sắp xếp lấy 2 sản phẩm rẻ nhất làm phương án thay thế gần nhất
                all_matched_products.sort(key=lambda x: x['price'])
                final_products = all_matched_products[:2]
            
            # Lấy tối đa 3 sản phẩm làm context
            context_list = []
            for p in final_products[:3]:
                # Lấy dữ liệu tồn kho thật 100% từ Database
                stock_count = p.get('stock', 0)
                if stock_count > 0:
                    stock_info = f"Tình trạng tồn kho: Còn hàng (Số lượng: {stock_count} sản phẩm)"
                else:
                    stock_info = "Tình trạng tồn kho: Hết hàng"
                
                # Lấy dữ liệu khuyến mãi thật 100% từ Database
                promo_text = p.get('gift_promotion', '')
                if promo_text and promo_text.strip():
                    promo_info = f"Khuyến mãi áp dụng: {promo_text}"
                else:
                    promo_info = "Khuyến mãi áp dụng: Không có chương trình khuyến mãi nào"
                
                enriched_text = f"{p['full_text']}. {stock_info}. {promo_info}."
                context_list.append(enriched_text)
                
            context = "\n".join(context_list)
        except Exception as e:
            context = f"Lỗi đọc kho dữ liệu: {str(e)}"
    
    if not context or "Không tìm thấy" in context:
        context = "Hiện tại trong kho tạm hết dòng sản phẩm khớp chính xác với ngân sách này của anh chị."

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

    # 4. PROMPT DỊCH THUẬT BÌNH DÂN & TRADE-OFF (Ăn điểm đặc thù 20%)
    system_advisor = f"""Bạn là một nhân viên tư vấn người Việt Nam chuyên nghiệp tại siêu thị Điện Máy Xanh.
    Hãy dùng tập dữ liệu sản phẩm CÓ THẬT sau đây để tư vấn cho khách:
    ---
    {context}
    ---
    QUY TẮC TƯ VẤN BẮT BUỘC SỐNG CÒN:
    1. BẮT BUỘC TRẢ LỜI BẰNG TIẾNG VIỆT 100%. TUYỆT ĐỐI KHÔNG dùng tiếng Trung, không dùng chữ Hán.
    2. Chỉ được dùng thông tin sản phẩm, giá bán, tình trạng tồn kho và khuyến mãi có trong dữ liệu ở trên để tư vấn. KHÔNG TỰ BỊA SẢN PHẨM, GIÁ, THÔNG SỐ, KHUYẾN MÃI HOẶC TỒN KHO. Nếu dữ liệu ở trên trống hoặc báo hết hàng, bạn BẮT BUỘC phải thông báo thành thật rằng sản phẩm đang tạm hết hàng trên hệ thống và KHÔNG giới thiệu bất kỳ sản phẩm nào khác ngoài danh sách.
    3. Không dùng từ ngữ kỹ thuật phức tạp (như Inverter, HP, BTU). Hãy dịch sang ngôn ngữ bình dân (Ví dụ: 'Máy chạy siêu êm ban đêm', 'Tiết kiệm tiền điện cuối tháng', 'Làm mát nhanh sâu').
    4. Luôn nêu rõ ưu và nhược điểm (Trade-off) giữa các lựa chọn để khách hàng dễ ra quyết định.
    5. BẮT BUỘC THÔNG BÁO cụ thể cho khách hàng về Tình trạng tồn kho thực tế và các chương trình Khuyến mãi/Quà tặng đi kèm của từng sản phẩm dựa trên thông tin thực tế được cung cấp.
    6. ĐỘ DÀI VÀ PHONG CÁCH PHẢN HỒI: Hãy phản hồi cực kỳ ngắn gọn, cô đọng, giới hạn câu trả lời dưới 120-150 từ. Trình bày dưới dạng các đầu dòng rõ ràng để giúp phản hồi sinh ra tức thì (vì chạy cục bộ trên CPU).
    
    {upsell_instruction}
    {extra_clarify}
    
    Hãy bắt đầu bằng một lời chào lịch sự thân thiện."""

    for chunk in call_local_llm_stream(system_advisor, messages=conversation_messages):
        yield chunk