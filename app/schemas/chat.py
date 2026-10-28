from uuid import UUID
from typing import Literal, Annotated, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator, StringConstraints


NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    ) 

    user_id: str
    message: str
    start_conversation: bool
    session_id: str | None = None
    role: str
    source: Literal["mobile_app", "web_app"]
    employee_type: Literal["direct", "indirect", ""] = Field(...)
    selected_payment_plan_names: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_session(self):
        if not self.user_id.strip():
            raise ValueError("user_id cannot be blank")

        if not self.message.strip():
            raise ValueError("message cannot be blank")

        if not self.role.strip():
            raise ValueError("Role cannot be blank")

        if (
            not self.start_conversation
            and self.session_id is None
        ):
            raise ValueError(
                "session_id is required when "
                "start_conversation is false"
            )

        return self
    

class ChatResponse(BaseModel):
    response: str
    session_id: UUID
    correlation_id: str
    followups: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)