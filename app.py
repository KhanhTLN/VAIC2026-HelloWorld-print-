import re
import os
import requests
import streamlit as st

# Cấu hình URL backend qua biến môi trường (mặc định chạy local ở port 8001)
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")

# 1. Cấu hình tiêu đề trang web
st.set_page_config(page_title="Trợ lý AI Điện Máy Xanh", page_icon="⚡", layout="centered")

st.markdown("""
<style>
div[data-testid="stChatInput"] > div {
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
div[data-testid="stChatInput"] button[kind="primary"] {
    border-radius: 999px;
    min-width: 2.8rem;
}
div[data-testid="stChatInput"] .stButton > button {
    background: linear-gradient(90deg, #ff6b2c, #ff8e3c);
    color: white;
    border: none;
    border-radius: 999px;
    padding: 0.45rem 0.8rem;
    font-weight: 700;
    box-shadow: 0 6px 16px rgba(255, 107, 44, 0.28);
}
</style>
""", unsafe_allow_html=True)

st.title("⚡ Trợ lý AI Tư vấn Điện Máy Xanh")
st.caption("Giao diện Frontend Trợ lý AI - Thử nghiệm mua sắm thông minh VAIC 2026")
st.caption("💡 Muốn đổi sản phẩm hoặc bắt đầu lại câu chuyện tư vấn? Bấm nút 🔄 Tải lại ở cuối khung chat trước khi hỏi tiếp.")
st.write("---")

WELCOME_MESSAGE = "Dạ Điện Máy Xanh xin chào anh/chị! Em có thể giúp gì cho anh/chị trong việc lựa chọn các sản phẩm điện thoại, máy lạnh, tủ lạnh hôm nay ạ?"

# 2. Khởi tạo lịch sử chat lưu trong bộ nhớ trình duyệt
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]


def reset_chat_session():
    st.session_state.messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]
    if "expanded_messages" in st.session_state:
        st.session_state.expanded_messages = {}
    st.rerun()


def render_reload_control(key_suffix):
    col1, col2 = st.columns([1, 6])
    with col1:
        if st.button("🔄", key=f"reload_chat_button_{key_suffix}", help="Làm mới cuộc trò chuyện để đổi sản phẩm hoặc bắt đầu lại từ đầu"):
            reset_chat_session()
    with col2:
        st.caption("Bấm reload khi bạn muốn tìm hiểu về những loại sản phẩm khác")


COLLAPSIBLE_PREVIEW_MARKER = "__PREVIEW__"
COLLAPSIBLE_END_PREVIEW_MARKER = "__END_PREVIEW__"
COLLAPSIBLE_FULL_MARKER = "__FULL__"
COLLAPSIBLE_END_FULL_MARKER = "__END_FULL__"


def parse_collapsible_sections(content):
    if not content:
        return None, None

    if (COLLAPSIBLE_PREVIEW_MARKER not in content or COLLAPSIBLE_FULL_MARKER not in content):
        return None, None

    try:
        preview_content = content.split(COLLAPSIBLE_PREVIEW_MARKER, 1)[1].split(COLLAPSIBLE_END_PREVIEW_MARKER, 1)[0].strip()
        full_content = content.split(COLLAPSIBLE_FULL_MARKER, 1)[1].split(COLLAPSIBLE_END_FULL_MARKER, 1)[0].strip()
        return preview_content, full_content
    except IndexError:
        return None, None


def format_product_specs(text):
    """
    Tự động phát hiện đoạn thông số dài ngăn cách bằng dấu '-'
    Bẻ xuống dòng, gạch đầu dòng từng tiêu chí và in đậm phần tiêu đề trước dấu ':'
    """
    if not text:
        return ""
    
    # SỬA LỖI: Nếu dòng này chứa thẻ ảnh Markdown hoặc liên kết ảnh, bỏ qua hoàn toàn không format tránh làm hỏng cấu trúc url
    if "![" in text or "http" in text:
        return text
        
    # Nếu dòng chứa quá nhiều dấu ' - ' (dấu hiệu của chuỗi thông số dính liền trên 1 dòng)
    if text.count(" - ") > 3 or (text.strip().startswith("* ") and text.count(" - ") > 2):
        cleaned = text.strip()
        if cleaned.startswith("*") or cleaned.startswith("-"):
            cleaned = cleaned[1:].strip()
            
        # Tách nhỏ các tiêu chí ra thành list
        items = [item.strip() for item in cleaned.split(" - ") if item.strip()]
        
        formatted_lines = []
        for item in items:
            # Nếu tiêu chí có dấu ":" (Ví dụ: "RAM: 8 GB") -> In đậm phần trước dấu ":"
            if ":" in item:
                key, value = item.split(":", 1)
                formatted_lines.append(f"* **{key.strip()}**: {value.strip()}")
            else:
                formatted_lines.append(f"* {item}")
                
        return "\n".join(formatted_lines)
        
    # Trường hợp dòng đơn bình thường nhưng có dấu ":" thì vẫn in đậm tiêu chí
    elif ":" in text and not text.strip().startswith("#"):
        parts = text.split(":", 1)
        prefix = ""
        main_text = parts[0]
        
        # Giữ nguyên định dạng gạch đầu dòng cũ của markdown nếu có
        if main_text.strip().startswith("*"):
            prefix = "* "
            main_text = main_text.replace("*", "", 1).strip()
        elif main_text.strip().startswith("-"):
            prefix = "- "
            main_text = main_text.replace("-", "", 1).strip()
            
        return f"{prefix}**{main_text.strip()}**: {parts[1].strip()}"

    return text


def deduplicate_markdown_text(text):
    """
    Xử lý liệt kê từng dòng, lọc trùng lặp và cấu trúc lại thông tin
    """
    if not text:
        return ""
        
    dedup_lines = []
    seen_lines = set()
    
    for line in text.splitlines():
        cleaned_line = line.strip()
        # Giữ lại các dòng trống để bảo toàn cấu trúc xuống dòng nguyên bản của Markdown
        if not cleaned_line:
            dedup_lines.append("")
            continue
            
        # Format bẻ dòng và in đậm
        formatted_line = format_product_specs(line)
        
        # Duyệt qua các dòng sau khi bẻ để loại bỏ phần tử bị trùng lặp
        sub_lines = formatted_line.splitlines()
        for sub_line in sub_lines:
            sub_cleaned = sub_line.strip()
            
            # SỬA LỖI: Không áp dụng cơ chế lọc trùng lặp cho các dòng chứa ảnh để đảm bảo tất cả ảnh đều được render đầy đủ
            if "![" in sub_cleaned:
                dedup_lines.append(sub_line)
                continue
                
            if sub_cleaned in seen_lines:
                continue
            if sub_cleaned:
                seen_lines.add(sub_cleaned)
            dedup_lines.append(sub_line)
        
    return "\n".join(dedup_lines).strip()


def render_chat_content(content, expanded=False, toggle_key=None):
    if not content:
        return

    # 1. Phân tách nội dung thu gọn/mở rộng
    preview_content, full_content = parse_collapsible_sections(content)
    display_content = full_content if (expanded and full_content) else preview_content or content

    # Loại bỏ sạch sẽ các tag kỹ thuật thừa nếu có để tránh lộ trên UI
    for marker in [COLLAPSIBLE_PREVIEW_MARKER, COLLAPSIBLE_END_PREVIEW_MARKER, COLLAPSIBLE_FULL_MARKER, COLLAPSIBLE_END_FULL_MARKER]:
        display_content = display_content.replace(marker, "")

    # 2. Xử lý định dạng lại thông tin từng dòng & lọc trùng
    display_content = deduplicate_markdown_text(display_content)

    # 3. Render nội dung (Cú pháp Markdown chuẩn tự động hiển thị hình ảnh inline rất mượt mà)
    if display_content:
        st.markdown(display_content, unsafe_allow_html=True)

    # 4. Nút bấm xem thêm/ẩn bớt
    if preview_content and full_content and toggle_key is not None:
        button_label = "Ẩn bớt" if expanded else "Xem tiếp"
        if st.button(button_label, key=toggle_key, help="Mở rộng hoặc thu gọn nội dung chi tiết"):
            expanded_state = st.session_state.setdefault("expanded_messages", {})
            expanded_state[toggle_key] = not expanded
            st.rerun()


# Hàm xử lý việc dọn dẹp nội dung thô khi đang stream
def clean_streaming_text(text):
    """Giúp ẩn các tag marker kỹ thuật ngay trong quá trình đang stream"""
    for marker in [COLLAPSIBLE_PREVIEW_MARKER, COLLAPSIBLE_END_PREVIEW_MARKER, COLLAPSIBLE_FULL_MARKER, COLLAPSIBLE_END_FULL_MARKER]:
        text = text.replace(marker, "")
    return text


def get_backend_stream(message, history):
    try:
        payload = {
            "message": message,
            "history": history[:-1]
        }
        response = requests.post(
            f"{BACKEND_URL}/api/chat",
            json=payload,
            stream=True,
            timeout=120
        )
        if response.status_code == 200:
            for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    yield chunk
        else:
            yield f"⚠️ Lỗi kết nối đến Backend: Mã lỗi {response.status_code}."
    except Exception as e:
        yield f"⚠️ Không thể kết nối tới server Backend ({BACKEND_URL}). (Chi tiết lỗi: {str(e)})"


# 4. Tiếp nhận câu hỏi mới
user_input = st.chat_input("Nhập nhu cầu của anh/chị tại đây...")

# 3. Hiển thị lại các câu chat cũ từ lịch sử
latest_ai_index = max((index for index, message in enumerate(st.session_state.messages) if message["role"] == "assistant"), default=None)
for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            expanded_state = st.session_state.setdefault("expanded_messages", {})
            toggle_key = f"assistant_{index}"
            expanded = expanded_state.get(toggle_key, False)
            render_chat_content(message["content"], expanded=expanded, toggle_key=toggle_key)
        else:
            st.markdown(message["content"])

        if not user_input and message["role"] == "assistant" and index == latest_ai_index:
            render_reload_control(f"history_{index}")

# Xử lý khi người dùng gửi tin nhắn mới
if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    with st.chat_message("assistant"):
        placeholder = st.empty()
        ai_response = ""

        for chunk in get_backend_stream(user_input, st.session_state.messages):
            ai_response += chunk
            clean_text = clean_streaming_text(ai_response)
            # Tách dòng, gạch đầu dòng và in đậm tiêu chí trực tiếp khi đang stream
            clean_text = deduplicate_markdown_text(clean_text)
            placeholder.markdown(clean_text)

    st.session_state.messages.append({"role": "assistant", "content": ai_response})
    st.rerun()