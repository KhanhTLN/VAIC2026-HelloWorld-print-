# Trợ lý AI Điện Máy Xanh - Vietnam Innovation Challenge 2026

## 1. Cài đặt môi trường
```bash
pip install -r requirements.txt
```

## 2. Khởi chạy ứng dụng

Kiến trúc ứng dụng đã được tách riêng độc lập thành **Backend** (xử lý RAG/LLM) và **Frontend** (giao diện người dùng):

### Bước 2.1: Chạy Backend (FastAPI)
Chạy lệnh sau tại thư mục gốc để khởi chạy API Server (mặc định chạy tại `http://127.0.0.1:8001`):
```bash
python server.py
```

### Bước 2.2: Chạy Frontend (Streamlit)
Mở một Terminal mới và chạy câu lệnh sau tại thư mục gốc để khởi động giao diện web:
```bash
streamlit run app.py
```

