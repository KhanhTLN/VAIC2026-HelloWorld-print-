import sys
import os

# Thêm thư mục hiện tại vào sys.path để import src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.agents.agent_logic import generate_advisor_response_stream, analyze_intent_fast

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
