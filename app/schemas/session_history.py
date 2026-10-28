"""
Pydantic response schemas for Danube Chatbot
session management and conversation history.

These schemas define the JSON returned to the frontend.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# 1. Individual chat message
class HistoryMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime
    response_payload: dict | None = None



# 2. Session information
class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None = None
    created_at: datetime
    last_activity_at: datetime
    status: str

    requires_confirmation: bool = False



# 3. Latest session API response
class LatestSessionResponse(BaseModel):
    session: SessionSummary | None = None
    messages: list[HistoryMessage] = Field(
        default_factory=list
    )
    has_more: bool = False



# 4. Chat history API response
class SessionHistoryResponse(BaseModel):

    session_id: UUID
    requires_confirmation: bool

    messages: list[HistoryMessage] = Field(
        default_factory=list
    )

    limit: int = 50
    offset: int = 0
    has_more: bool = False


# 5. Resume session API response
class ResumeSessionResponse(BaseModel):
    session_id: UUID
    status: str = "active"
    requires_confirmation: bool = False
    last_activity_at: datetime

    messages: list[HistoryMessage] = Field(
        default_factory=list
    )
    has_more: bool = False
