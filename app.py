import streamlit as st
import sys
import os

# Thêm đường dẫn thư mục gốc vào hệ thống để import được file agent_logic.py
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import importlib
import src.agents.agent_logic as agent_logic
importlib.reload(agent_logic)
from src.agents.agent_logic import generate_advisor_response_stream

# 1. Cấu hình tiêu đề trang web
st.set_page_config(page_title="Trợ lý AI Điện Máy Xanh", page_icon="⚡", layout="centered")

st.title("⚡ Trợ lý AI Tư vấn Điện Máy Xanh")
st.caption("Hệ thống trợ lý AI chạy Local - Thử nghiệm mô hình mua sắm thông minh VIC 2026")
st.write("---")

# 2. Khởi tạo lịch sử chat lưu trong bộ nhớ trình duyệt
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Dạ Điện Máy Xanh xin chào anh/chị! Em có thể giúp gì cho anh/chị trong việc lựa chọn các sản phẩm điện thoại, máy lạnh, tủ lạnh hôm nay ạ?"}
    ]

# 3. Hiển thị lại các câu chat cũ ra màn hình giao diện web
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 4. Tiếp nhận câu hỏi mới từ người dùng nhập vào ô chat
if user_input := st.chat_input("Nhập nhu cầu của anh/chị tại đây..."):
    
    # Hiển thị câu chat của người dùng
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Kích hoạt bộ não AI chạy local xử lý câu trả lời
    with st.chat_message("assistant"):
        ai_response = st.write_stream(generate_advisor_response_stream(user_input, history=st.session_state.messages))
            
    # Lưu câu trả lời của AI vào lịch sử chat
    st.session_state.messages.append({"role": "assistant", "content": ai_response})
