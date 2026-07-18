import json
import os
import urllib.error
import urllib.request

import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


def request_backend_answer(user_message: str, history: list[dict[str, str]]) -> str:
    payload = json.dumps({"message": user_message, "history": history}).encode("utf-8")
    request = urllib.request.Request(
        f"{BACKEND_URL}/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body.get("answer", "")
    except urllib.error.URLError:
        return "Không thể kết nối backend. Vui lòng chạy API server trước khi chat."

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
    
    # Gọi backend API để xử lý câu trả lời
    with st.chat_message("assistant"):
        ai_response = request_backend_answer(user_input, st.session_state.messages)
        st.markdown(ai_response)

    # Lưu câu trả lời của AI vào lịch sử chat
    st.session_state.messages.append({"role": "assistant", "content": ai_response})
