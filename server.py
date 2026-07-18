import sys
import os
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional

# Thêm đường dẫn thư mục gốc vào hệ thống để import được module src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.agents.agent_logic import generate_advisor_response_stream

app = FastAPI(
    title="⚡ API Trợ lý AI Điện Máy Xanh",
    description="Hệ thống Backend xử lý RAG & LLM local tích hợp dữ liệu Supabase",
    version="1.0.0"
)

# Cấu hình CORS để cho phép frontend gọi từ các domain khác (như Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    # Chuyển đổi lịch sử chat sang định dạng dict mà agent_logic yêu cầu
    formatted_history = []
    if request.history:
        for msg in request.history:
            formatted_history.append({
                "role": msg.role,
                "content": msg.content
            })
            
    # Tạo generator streaming dữ liệu text/plain trả về cho client
    def event_generator():
        for chunk in generate_advisor_response_stream(request.message, history=formatted_history):
            yield chunk

    return StreamingResponse(event_generator(), media_type="text/plain")

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # Sử dụng cổng 8001 để tránh xung đột cổng 8000 trên hệ thống
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)
