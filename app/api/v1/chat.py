import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Depends, Header
from fastapi.responses import StreamingResponse
from typing import Annotated
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.schemas.chat import ChatRequest
from app.services.streaming_service import stream_chat_response
from app.core.dependencies import get_session_service
from app.services.session_service import SessionService, SessionNotFoundError, SessionResumeRequiredError
from app.observability.logger import audit_event

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Enter the access token issued by Danube authentication."
)

logger = logging.getLogger(__name__)


@router.post("/query")
async def chat_query(
    body: ChatRequest,
    request: Request,
    session_service: Annotated[
        SessionService,
        Depends(get_session_service),
    ],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme)
    ],

) -> StreamingResponse:

    if credentials is None or not credentials.credentials.strip():
        raise HTTPException(
            status_code=401,
            detail="Authorization token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Bearer authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )


    correlation_id = getattr(
        request.state,
        "correlation_id",
        str(uuid.uuid4()),
    )

    clients = request.app.state.clients

    audit_event(
        "CHAT_REQUEST_RECEIVED",
        correlation_id=correlation_id,
        user_id=body.user_id,
        role=body.role,
        source=body.source,
        user_message=body.message,
        start_conversation=body.start_conversation,
        session_id=str(body.session_id) if body.session_id else None,
    )

    # 1. SESSION HANDLING

    if body.start_conversation:

        session = await session_service.create_session(
            user_id=body.user_id,
            user_role=body.role,
            source=body.source,
            title=body.message.strip()[:100],
        )

        session_id = session.id

        logger.info(
            "CHAT_SESSION_CREATED | "
            "correlation_id=%s | "
            "session_id=%s",
            correlation_id,
            session_id,
        )

    else:

        if body.session_id is None:
            raise HTTPException(
                status_code=422,
                detail="session_id is required",
            )

        try:
            await session_service.admit_chat_message(
                session_id=body.session_id,
                user_id=body.user_id,
                inactivity_minutes=30,
            )

        except SessionResumeRequiredError:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SESSION_RESUME_REQUIRED",
                    "message": (
                        "Your previous conversation has been "
                        "inactive for 30 minutes. "
                        "Please choose Continue or New Chat."
                    ),
                    "session_id": str(body.session_id),
                },
            )

        except SessionNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        session_id = body.session_id

        logger.info(
            "CHAT_SESSION_RESUMED | "
            "session_id=%s | correlation_id=%s",
            session_id,
            correlation_id,
        )

    audit_event(
        "CHAT_SESSION_READY",
        correlation_id=correlation_id,
        session_id=str(session_id),
        user_id=body.user_id,
        status="ready",
    )

    # 2. NORMAL CHATBOT STREAMING

    access_token = credentials.credentials.strip()
    walkthrough_engine = request.app.state.walkthrough_engine

    stream_kwargs = {
        "message": body.message,
        "session_id": session_id,
        "correlation_id": correlation_id,
        "user_id": body.user_id,
        "role": body.role,
        "source": body.source,
        "employee_type": body.employee_type,
        "clients": clients,
        "access_token": access_token,
        "walkthrough_engine": walkthrough_engine,
        "selected_payment_plan_names": body.selected_payment_plan_names,
    }

    if body.selected_payment_plan_names:
        stream_kwargs["selected_payment_plan_names"] = (
            body.selected_payment_plan_names
        )

    return StreamingResponse(
        stream_chat_response(**stream_kwargs),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
