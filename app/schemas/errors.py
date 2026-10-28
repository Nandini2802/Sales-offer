from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    session_id: str | None = None
    correlation_id: str
    retryable: bool = False


class ErrorResponse(BaseModel):
    error: ErrorDetail