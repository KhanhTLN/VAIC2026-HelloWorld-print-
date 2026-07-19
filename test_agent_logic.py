import sys
import os

# Thêm thư mục hiện tại vào sys.path để import src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.agents.agent_logic import (
    generate_advisor_response_stream,
    analyze_intent_fast,
    detect_specific_model_request,
    reset_intent_state_on_category_change,
    filter_history_for_current_category,
    db_search_products,
)

def test_query(user_message, history=None):
    print(f"\n======================================")
    print(f"QUERY: '{user_message}'")
    print(f"HISTORY: {history}")
    
    # In ra intent phân tích được để debug
    intent = analyze_intent_fast(user_message)
    print(f"DETECTED INTENT: {intent}")
    
    # Chạy stream phản hồi từ agent
    print("AI RESPONSE STREAM:")
    try:
        stream = generate_advisor_response_stream(user_message, history=history)
        for chunk in stream:
            print(chunk, end="", flush=True)
        print()
    except Exception as e:
        print(f"\nError: {e}")

def test_detect_specific_model_request():
    result = detect_specific_model_request("tư vấn giúp tôi iphone 15 pro max")
    assert result["is_specific_model"] is True
    assert result["requested_model"] == "iphone 15 pro max"


def test_reset_intent_state_on_category_change():
    prev_state = {
        "category": "dien-thoai",
        "brand": "apple",
        "budget": 15000000,
        "room_size": None,
        "family_members": None,
        "laptop_needs": None,
        "headphone_needs": None,
        "phone_needs": None,
        "product_query": "tư vấn điện thoại",
    }
    current_intent = {
        "category": "may-lanh",
        "brand": None,
        "budget": None,
        "room_size": "20m2",
        "family_members": None,
        "laptop_needs": None,
        "headphone_needs": None,
        "phone_needs": None,
    }

    new_state = reset_intent_state_on_category_change(prev_state, current_intent)
    assert new_state["category"] == "may-lanh"
    assert new_state["brand"] is None
    assert new_state["budget"] is None
    assert new_state["room_size"] == "20m2"
    assert new_state["product_query"] is None


def test_filter_history_for_current_category():
    history = [
        {"role": "user", "content": "tư vấn iphone 17 pro max"},
        {"role": "assistant", "content": "Anh chị có thể cho biết số người sử dụng không?"},
        {"role": "user", "content": "tư vấn tủ lạnh"},
    ]
    filtered = filter_history_for_current_category(history, "tư vấn tủ lạnh")
    assert filtered == []


def test_db_search_products_falls_back_to_local_catalog_when_db_unavailable(monkeypatch):
    def raise_db_error(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("src.agents.agent_logic.get_db_connection", raise_db_error)

    context, is_upsell, top_relevance, matched_products = db_search_products(
        "dien-thoai", "apple", None, "iphone 17 pro max"
    )

    assert is_upsell is False
    assert top_relevance >= 0
    assert matched_products, "expected fallback catalog products when DB is unavailable"
    assert any("iPhone 17 Pro Max" in product["name"] for product in matched_products)
    assert "iPhone 17 Pro Max" in context


if __name__ == "__main__":
    # Test 1: Chỉ hỏi chung chung về ngành hàng điện thoại (Chưa thương hiệu, chưa spec -> Phải hỏi làm rõ ít nhất 2 tiêu chí)
    test_query("tư vấn điện thoại")
    
    # Test 2: Hỏi điện thoại kèm thương hiệu (Đã biết brand -> Chỉ cần hỏi làm rõ ít nhất 1 tiêu chí nữa)
    test_query("tư vấn điện thoại samsung")
    
    # Test 3: Đã có brand và budget (Đủ tiêu chí tư vấn trực tiếp)
    test_query("tư vấn điện thoại iphone giá dưới 15 triệu")
    
    # Test 4: Đã có budget và nhu cầu chụp ảnh (Đủ 2 tiêu chí cho brand chưa biết -> Tư vấn trực tiếp)
    test_query("tư vấn điện thoại chụp hình đẹp giá dưới 7 triệu")
    
    # Test 5: Hỏi model cụ thể (Tư vấn trực tiếp)
    test_query("tư vấn iPhone 16 Pro Max")
    
    # Test 6: Hỏi model cụ thể bị hết hàng hoàn toàn (Phải xin lỗi và gợi ý sản phẩm thay thế cùng hãng có giá gần nhất)
    test_query("tư vấn giúp tôi iphone 15 pro max")
