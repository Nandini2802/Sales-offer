
"""
Pydantic schemas for chatbot session APIs.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=255,
    )


class UpdateSessionRequest(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=255,
    )


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime


class SessionDetailResponse(SessionResponse):
    messages: list[MessageResponse]


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]


class QueryLogRequest(BaseModel):
    query_text: str = Field(
        min_length=1,
        max_length=20000,
    )
    intent: str | None = Field(
        default=None,
        max_length=100,
    )
    status: str = Field(
        default="pending",
        max_length=30,
    )
    latency_ms: int | None = Field(
        default=None,
        ge=0,
    )


class QueryLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    user_id: str
    query_text: str
    intent: str | None
    status: str
    latency_ms: int | None
    created_at: datetime
