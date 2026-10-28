from typing import Any, Literal
from pydantic import BaseModel, Field


class SessionEvent(BaseModel):
    session_id: str
    correlation_id: str


class TokenEvent(BaseModel):
    text: str


class HTMLBlockEvent(BaseModel):
    type: Literal["html_block"] = "html_block"
    card_type: str
    html: str


class FollowupsEvent(BaseModel):
    chips: list[str] = Field(default_factory=list)


class DoneEvent(BaseModel):
    status: Literal["completed", "failed"]