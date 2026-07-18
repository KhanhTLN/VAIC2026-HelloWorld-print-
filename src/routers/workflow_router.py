from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflow", tags=["workflow"])
service = WorkflowService()


class WorkflowRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)


@router.post("/query")
def query_workflow(payload: WorkflowRequest):
    result = service.run(user_message=payload.message, history=payload.history)
    return result.model_dump()
