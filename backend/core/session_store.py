from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatSession:
    session_id: str
    category_name: str | None
    category_id: int | None
    # Real JSONB keys available for this category (from DB).
    spec_keys: list[str] = field(default_factory=list)
    # Collected criteria: brand / max_price / min_price / <spec_key> -> value
    criteria: dict[str, Any] = field(default_factory=dict)
    # Field we just asked about (so free-text answer maps here).
    pending_field: str | None = None
    asked_fields: list[str] = field(default_factory=list)
    target_criteria: int = 2
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class SessionStore:
    """In-memory session store for dynamic consult chat."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    def create(
        self,
        *,
        category_name: str | None,
        category_id: int | None,
        spec_keys: list[str],
        target_criteria: int = 2,
    ) -> ChatSession:
        session_id = uuid.uuid4().hex
        session = ChatSession(
            session_id=session_id,
            category_name=category_name,
            category_id=category_id,
            spec_keys=spec_keys,
            target_criteria=target_criteria,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    def save(self, session: ChatSession) -> None:
        session.updated_at = time.time()
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


session_store = SessionStore()
