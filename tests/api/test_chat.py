from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import chat
from app.core.dependencies import get_session_service


@pytest.mark.parametrize("start_conversation", [True, False])
def test_chat_audits_payload_and_streams_response(monkeypatch, start_conversation):
    session_id = "test-session"
    correlation_id = "test-correlation"
    session_service = SimpleNamespace(
        create_session=AsyncMock(return_value=SimpleNamespace(id=session_id)),
        admit_chat_message=AsyncMock(),
    )
    audit = Mock()

    async def fake_stream(**kwargs):
        yield "data: test-response\n\n"

    stream = Mock(side_effect=fake_stream)
    monkeypatch.setattr(chat, "audit_event", audit)
    monkeypatch.setattr(chat, "stream_chat_response", stream)

    app = FastAPI()
    app.state.clients = object()
    app.state.walkthrough_engine = object()
    app.dependency_overrides[get_session_service] = lambda: session_service

    @app.middleware("http")
    async def set_correlation_id(request, call_next):
        request.state.correlation_id = correlation_id
        return await call_next(request)

    app.include_router(chat.router, prefix="/api/v1")
    payload = {
        "user_id": "test-user",
        "message": "Hello",
        "role": "customer",
        "source": "web_app",
        "employee_type": "",
        "start_conversation": start_conversation,
        "session_id": None if start_conversation else session_id,
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/chat/query", json=payload)

    assert response.status_code == 200
    assert response.text == "data: test-response\n\n"
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["X-Correlation-ID"] == correlation_id
    audit.assert_called_once_with(
        "CHAT_REQUEST_RECEIVED",
        correlation_id=correlation_id,
        user_id=payload["user_id"],
        role=payload["role"],
        source=payload["source"],
        user_message=payload["message"],
    )
    assert stream.call_args.kwargs["session_id"] == session_id
    assert stream.call_args.kwargs["message"] == payload["message"]
    if start_conversation:
        session_service.create_session.assert_awaited_once_with(
            user_id=payload["user_id"],
            user_role=payload["role"],
            source=payload["source"],
            title=payload["message"],
        )
        session_service.admit_chat_message.assert_not_awaited()
    else:
        session_service.admit_chat_message.assert_awaited_once_with(
            session_id=session_id,
            user_id=payload["user_id"],
            inactivity_minutes=30,
        )
        session_service.create_session.assert_not_awaited()
