from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.routers.workflow_router import router as workflow_router
from src.services.workflow_service import WorkflowService

app = FastAPI(title="Dien May Xanh AI Backend", version="1.0.0")
app.include_router(workflow_router)

_workflow_service = WorkflowService()


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    answer = "".join(_workflow_service.run_stream(user_message=payload.message, history=payload.history))
    return ChatResponse(answer=answer)
