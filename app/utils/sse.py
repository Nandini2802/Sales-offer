import json
from typing import Any


def format_sse(event: str, data: Any) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


def session_event(data: dict) -> str:
    return format_sse("session", data)


def token_event(text: str) -> str:
    return format_sse("token", {"text": text})


def final_event(data: dict) -> str:
    return format_sse("final", data)


def error_event(code: str, message: str) -> str:
    return format_sse(
        "error",
        {"code": code, "message": message},
    )


def done_event() -> str:
    return format_sse(
        "done",
        {"status": "completed"},
    )