"""
Session Management APIs - Danube Properties Chatbot.

Responsibilities:
- Create a chat session
- List sessions for a user
- Retrieve session details and history
- Update a session title
- Delete a session
- Retrieve conversation messages
- Retrieve recent conversation context

Authentication will be integrated separately.
"""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from app.core.dependencies import get_session_service
from app.schemas.session import *
from app.services.session_service import *
from app.schemas.session_history import *
from app.services.session_timeout_service import *


router = APIRouter(
    prefix="/sessions",
    tags=["Sessions"],
)

Service = Annotated[
    SessionService,
    Depends(get_session_service),
]

CurrentUser = Annotated[
    str,
    Query(
        min_length=1,
        description="Salesforce User ID (development only)",
    ),
]

# 1. Create Session

@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: CreateSessionRequest,
    user_id: CurrentUser,
    service: Service,
):
    """
    Create a new chat session for a user.
    """

    session = await service.create_session(
        user_id=user_id,
        title=payload.title,
    )

    return session


# 2. List User Sessions

@router.get(
    "",
    response_model=SessionListResponse,
)
async def list_sessions(
    user_id: CurrentUser,
    service: Service,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Retrieve sessions belonging to a user.
    """

    sessions = await service.list_sessions(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    return {
        "sessions": sessions,
    }


# 3. Get Latest User Session

@router.get(
    "/latest",
    response_model=LatestSessionResponse,
    status_code=status.HTTP_200_OK,
)
async def get_latest_session(
    user_id: CurrentUser,
    service: Service,
):
    session = await service.get_latest_session(
        user_id=user_id,
    )

    if session is None:
        return LatestSessionResponse(
            session=None,
            messages=[],
            has_more=False,
        )

    requires_confirmation = (
        session_requires_confirmation(
            session.last_activity_at
        )
    )

    result = await service.get_session_history(
        session_id=session.id,
        user_id=user_id,
        limit=50,
        offset=0,
    )

    return LatestSessionResponse(
        session=SessionSummary(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            last_activity_at=session.last_activity_at,
            status=session.status,
            requires_confirmation=requires_confirmation,
        ),
        messages=[
            HistoryMessage.model_validate(message)
            for message in result["messages"]
        ],
        has_more=result["has_more"],
    )


# 8. Get Full Conversation History

@router.get(
    "/{session_id}/history",
    response_model=SessionHistoryResponse,
)
async def get_session_history_api(
    session_id: UUID,
    user_id: CurrentUser,
    service: Service,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Retrieve saved messages for a session.

    Reading history does not reset inactivity.
    """

    try:
        result = await service.get_session_history(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

        session = result["session"]
        messages = result["messages"]

        return SessionHistoryResponse(
            session_id=session.id,
            requires_confirmation=(
                session_requires_confirmation(
                    session.last_activity_at
                )
            ),
            messages=[
                HistoryMessage.model_validate(message)
                for message in messages
            ],
            limit=limit,
            offset=offset,
            has_more=result["has_more"],
        )

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )


# 4. Get Session Details

@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
)
async def get_session(
    session_id: UUID,
    user_id: CurrentUser,
    service: Service,
):
    """
    Retrieve session details and message history.
    """

    try:
        session = await service.get_session(
            session_id=session_id,
            user_id=user_id,
        )

        messages = await service.get_history(
            session_id=session_id,
            user_id=user_id,
        )

        return {
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "messages": messages,
        }

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )


# 5. Update Session Title

@router.patch(
    "/{session_id}",
    response_model=SessionResponse,
)
async def update_session(
    session_id: UUID,
    payload: UpdateSessionRequest,
    user_id: CurrentUser,
    service: Service,
):
    """
    Update the title of an existing session.
    """

    try:
        return await service.update_session_title(
            session_id=session_id,
            user_id=user_id,
            title=payload.title,
        )

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

# 6. Delete Session

@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(
    session_id: UUID,
    user_id: CurrentUser,
    service: Service,
):
    """
    Delete a session and its related records.
    """

    try:
        await service.delete_session(
            session_id=session_id,
            user_id=user_id,
        )

        return Response(
            status_code=status.HTTP_204_NO_CONTENT,
        )

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

# 7. Get Conversation Messages

@router.get(
    "/{session_id}/messages",
    response_model=MessageListResponse,
)
async def get_messages(
    session_id: UUID,
    user_id: CurrentUser,
    service: Service,
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Retrieve messages for a particular session.
    """

    try:
        messages = await service.get_history(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )

        return {
            "messages": messages,
        }

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )


# 8. Get Recent Conversation Context

@router.get(
    "/{session_id}/context",
    response_model=list[dict[str, str]],
)
async def get_recent_context(
    session_id: UUID,
    user_id: CurrentUser,
    service: Service,
    message_limit: int = Query(
        default=10,
        ge=1,
        le=200,
    ),
):
    """
    Retrieve recent messages for future LLM context.
    """

    try:
        context = await service.get_recent_context(
            session_id=session_id,
            user_id=user_id,
            message_limit=message_limit,
        )

        return context

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )


# 9. Resume Existing Conversation

@router.post(
    "/{session_id}/resume",
    response_model=ResumeSessionResponse,
)
async def resume_chat_session(
    session_id: UUID,
    user_id: CurrentUser,
    service: Service,
):
    try:
        session = await service.resume_session(
            session_id=session_id,
            user_id=user_id,
        )

        result = await service.get_session_history(
            session_id=session_id,
            user_id=user_id,
            limit=50,
            offset=0,
        )

        return ResumeSessionResponse(
            session_id=session.id,
            status=session.status,
            requires_confirmation=False,
            last_activity_at=session.last_activity_at,
            messages=[
                HistoryMessage.model_validate(message)
                for message in result["messages"]
            ],
            has_more=result["has_more"],
        )

    except SessionNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )