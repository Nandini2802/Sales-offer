
import uuid

import pytest

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.exceptions import AppException
from app.middleware.correlation_id import correlation_id_middleware

from app.middleware.exception_handlers import (
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    unexpected_exception_handler,
)

from app.schemas.chat import ChatRequest, ChatResponse


# ==================================================
# 1. Create isolated test application
# ==================================================

@pytest.fixture
def client():

    app = FastAPI()

    # Register actual correlation ID middleware
    app.middleware("http")(correlation_id_middleware)

    # Register actual exception handlers
    app.add_exception_handler(
        AppException,
        app_exception_handler
    )

    app.add_exception_handler(
        HTTPException,
        http_exception_handler
    )

    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler
    )

    app.add_exception_handler(
        Exception,
        unexpected_exception_handler
    )

    # Sample endpoint to test schemas
    @app.post("/test/chat", response_model=ChatResponse)
    async def test_chat(payload: ChatRequest, request: Request):

        return ChatResponse(
            response="Message received successfully",
            session_id=payload.session_id or uuid.uuid4(),
            correlation_id=request.state.correlation_id,
        )

    # Sample endpoint to test custom exceptions
    @app.get("/test/custom-error")
    async def custom_error():

        raise AppException(
            message="Project not found",
            status_code=404,
            error_code="PROJECT_NOT_FOUND",
        )

    # Sample endpoint to test HTTP exceptions
    @app.get("/test/http-error")
    async def http_error():

        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    # Sample endpoint to test unexpected errors
    @app.get("/test/server-error")
    async def server_error():

        raise RuntimeError(
            "Sensitive internal database information"
        )

    with TestClient(
        app,
        raise_server_exceptions=False
    ) as test_client:
        yield test_client


# ==================================================
# 2. CORRELATION ID TESTS
# ==================================================

def test_correlation_id_generated(client):

    response = client.get("/test/http-error")

    correlation_id = response.headers.get(
        "X-Correlation-ID"
    )

    assert correlation_id is not None

    uuid.UUID(correlation_id)


def test_existing_correlation_id(client):

    existing_id = str(uuid.uuid4())

    response = client.get(
        "/test/http-error",
        headers={
            "X-Correlation-ID": existing_id
        },
    )

    assert response.headers["X-Correlation-ID"] == existing_id


def test_invalid_correlation_id(client):

    response = client.get(
        "/test/http-error",
        headers={
            "X-Correlation-ID": "invalid-id"
        },
    )

    new_id = response.headers["X-Correlation-ID"]

    assert new_id != "invalid-id"

    uuid.UUID(new_id)


# ==================================================
# 3. EXCEPTION HANDLER TESTS
# ==================================================

def test_custom_exception(client):

    response = client.get("/test/custom-error")

    assert response.status_code == 404

    data = response.json()

    assert data["error"]["code"] == "PROJECT_NOT_FOUND"
    assert data["error"]["message"] == "Project not found"

    assert data["error"]["correlation_id"] == (
        response.headers["X-Correlation-ID"]
    )


def test_http_exception(client):

    response = client.get("/test/http-error")

    assert response.status_code == 403

    data = response.json()

    assert data["error"]["code"] == "HTTP_ERROR"
    assert data["error"]["message"] == "Access denied"


def test_unexpected_exception(client):

    response = client.get("/test/server-error")

    assert response.status_code == 500

    data = response.json()

    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"

    # Internal exception details must not leak
    assert "Sensitive internal" not in response.text


# ==================================================
# 4. PYDANTIC SCHEMA TESTS
# ==================================================

def test_valid_chat_request(client):

    response = client.post(
        "/test/chat",
        json={
            "user_id": "broker_001",
            "message": "Tell me about Greenz",
            "start_conversation": True,
            "session_id": None
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["response"] == "Message received successfully"
    assert "session_id" in data
    assert "correlation_id" in data



def test_empty_message(client):

    response = client.post(
        "/test/chat",
        json={
            "message": ""
        },
    )

    assert response.status_code == 422


def test_missing_message(client):

    response = client.post(
        "/test/chat",
        json={},
    )

    assert response.status_code == 422


def test_message_too_long(client):

    response = client.post(
        "/test/chat",
        json={
            "message": "A" * 4001
        },
    )

    assert response.status_code == 422


def test_invalid_session_id(client):

    response = client.post(
        "/test/chat",
        json={
            "message": "Show available units",
            "session_id": "invalid-session-id"
        },
    )

    assert response.status_code == 422



def test_valid_session_id(client):

    session_id = str(uuid.uuid4())

    response = client.post(
        "/test/chat",
        json={
            "user_id": "broker_001",
            "message": "Show available units",
            "start_conversation": False,
            "session_id": session_id
        },
    )

    assert response.status_code == 200, response.text

    assert response.json()["session_id"] == session_id
