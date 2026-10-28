"""
Session management and conversation persistence.

Uses the existing PostgreSQL repositories.
"""

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
from sqlalchemy import update

from app.persistence.repositories.session_repo import SessionRepository
from app.persistence.repositories.chat_history_repo import ChatHistoryRepository
from app.persistence.repositories.query_log_repo import QueryLogRepository
from app.persistence.models import ChatSession , ChatMessage


class SessionNotFoundError(Exception):
    """Session is missing or inaccessible to this user."""


class InvalidMessageError(ValueError):
    """Invalid conversation message."""

class SessionResumeRequiredError(Exception):
    """Session requires user confirmation after inactivity."""

class SessionService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.session_repo = SessionRepository(db)
        self.history_repo = ChatHistoryRepository(db)
        self.query_log_repo = QueryLogRepository(db)

    @staticmethod
    def _validate_user(user_id: str) -> str:
        if not user_id or not user_id.strip():
            raise ValueError("User ID is required")
        return user_id.strip()

    async def _require_session(
        self,
        session_id: UUID,
        user_id: str,
    ):
        session = await self.session_repo.get_session(
            session_id=session_id,
            user_id=self._validate_user(user_id),
        )

        if session is None:
            raise SessionNotFoundError(
                "Session not found"
            )

        return session

    # SESSION OPERATIONS

    async def create_session(
        self,
        user_id: str,
        user_role: str = "broker",
        source: str | None = None,
        app_source: str | None = None,
        title: str | None = None,
    ):
        user_id = self._validate_user(user_id)

        try:
            session = (
                await self.session_repo.create_session(
                    user_id=user_id,
                    user_role=user_role,
                    source=source,
                    app_source=app_source,
                    title=title,
                )
            )

            await self.db.commit()
            await self.db.refresh(session)

            return session

        except Exception:
            await self.db.rollback()
            raise

    async def get_session(
        self,
        session_id: UUID,
        user_id: str,
    ):
        return await self._require_session(
            session_id,
            user_id,
        )

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ):
        return await self.session_repo.list_sessions(
            user_id=self._validate_user(user_id),
            limit=limit,
            offset=offset,
        )

    async def update_session_title(
        self,
        session_id: UUID,
        user_id: str,
        title: str,
    ):
        if not title or not title.strip():
            raise ValueError(
                "Session title cannot be empty"
            )

        if len(title) > 255:
            raise ValueError(
                "Session title is too long"
            )

        try:
            session = (
                await self.session_repo.update_session(
                    session_id=session_id,
                    user_id=self._validate_user(user_id),
                    title=title.strip(),
                )
            )

            if session is None:
                raise SessionNotFoundError(
                    "Session not found"
                )

            await self.db.commit()
            await self.db.refresh(session)

            return session

        except Exception:
            await self.db.rollback()
            raise

    async def delete_session(
        self,
        session_id: UUID,
        user_id: str,
    ) -> None:

        try:
            deleted = (
                await self.session_repo.delete_session(
                    session_id=session_id,
                    user_id=self._validate_user(user_id),
                )
            )

            if not deleted:
                raise SessionNotFoundError(
                    "Session not found"
                )

            await self.db.commit()

        except Exception:
            await self.db.rollback()
            raise

    async def admit_chat_message(
        self,
        session_id: UUID,
        user_id: str,
        inactivity_minutes: int = 30,
    ):
        """
        Check whether an existing session may accept
        a new message.

        If permitted, update its activity timestamp
        atomically before starting LLM processing.
        """

        user_id = self._validate_user(user_id)

        if inactivity_minutes <= 0:
            raise ValueError(
                "inactivity_minutes must be positive"
            )

        now = datetime.now(timezone.utc)

        cutoff = now - timedelta(
            minutes=inactivity_minutes
        )

        try:
            statement = (
                update(ChatSession)
                .where(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id,
                    ChatSession.status == "active",
                    ChatSession.last_activity_at >= cutoff,
                )
                .values(
                    last_activity_at=now,
                )
                .returning(ChatSession.id)
            )

            result = await self.db.execute(statement)
            admitted_id = result.scalar_one_or_none()

            if admitted_id is not None:
                await self.db.commit()
                return True

            # Determine whether the session is missing
            # or simply requires confirmation.
            session = await self._require_session(
                session_id=session_id,
                user_id=user_id,
            )

            if session.status != "active":
                raise SessionNotFoundError(
                    "Session not found"
                )

            raise SessionResumeRequiredError(
                "Session inactive for 30 minutes. "
                "Please confirm whether to continue."
            )

        except Exception:
            await self.db.rollback()
            raise
    
    
    # MESSAGE OPERATIONS

    async def save_message(
        self,
        session_id: UUID,
        user_id: str,
        role: str,
        content: str,
    ):
        if role not in ("user", "assistant"):
            raise InvalidMessageError(
                "Invalid message role"
            )

        if not content or not content.strip():
            raise InvalidMessageError(
                "Message cannot be empty"
            )

        try:
            message = (
                await self.history_repo.add_message(
                    session_id=session_id,
                    user_id=self._validate_user(user_id),
                    role=role,
                    content=content,
                )
            )

            if message is None:
                raise SessionNotFoundError(
                    "Session not found"
                )

            await self.db.commit()
            await self.db.refresh(message)

            return message

        except Exception:
            await self.db.rollback()
            raise

    async def get_history(
        self,
        session_id: UUID,
        user_id: str,
        limit: int = 50,
    ):
        await self._require_session(
            session_id,
            user_id,
        )

        return await self.history_repo.list_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )

    async def get_recent_context(
        self,
        session_id: UUID,
        user_id: str,
        message_limit: int = 10,
    ) -> list[dict]:

        await self._require_session(
            session_id,
            user_id,
        )

        messages = (
            await self.history_repo.get_recent_messages(
                session_id=session_id,
                user_id=user_id,
                limit=message_limit,
            )
        )

        return [
            {
                "role": item.role,
                "content": item.content,
            }
            for item in messages
        ]

    async def get_latest_inventory_context(
        self,
        session_id: UUID,
        user_id: str,
    ) -> dict | None:

        user_id = self._validate_user(user_id)

        await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

        statement = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
            )
            .order_by(
                ChatMessage.created_at.desc(),
                ChatMessage.id.desc(),
            )
            .limit(20)
        )

        result = await self.db.execute(statement)

        for record in result.scalars().all():
            payload = record.response_payload or {}

            if not isinstance(payload, dict):
                continue

            inventory_context = payload.get("inventory_context")

            if inventory_context:
                return inventory_context

        return None

    # QUERY LOG OPERATIONS

    async def log_query(
        self,
        session_id: UUID,
        user_id: str,
        query_text: str,
        intent: str | None = None,
        status: str = "pending",
        latency_ms: int | None = None,
    ):
        try:
            log = (
                await self.query_log_repo.create_query_log(
                    session_id=session_id,
                    user_id=self._validate_user(user_id),
                    query_text=query_text,
                    intent=intent,
                    status=status,
                    latency_ms=latency_ms,
                )
            )

            if log is None:
                raise SessionNotFoundError(
                    "Session not found"
                )

            await self.db.commit()
            await self.db.refresh(log)

            return log

        except Exception:
            await self.db.rollback()
            raise

    # ATOMIC COMPLETED EXCHANGE

    async def save_completed_exchange(
        self,
        session_id: UUID,
        user_id: str,
        user_message: str,
        assistant_message: str,
        intents: list[str],
        latency_ms: int | None = None,
        response_payload: dict | None = None,
    ):
        """
        Save user message, assistant message,
        and query log in one transaction.

        No partial conversation is committed.
        """

        user_id = self._validate_user(user_id)

        if not user_message.strip():
            raise InvalidMessageError(
                "User message cannot be empty"
            )

        if not assistant_message.strip():
            raise InvalidMessageError(
                "Assistant message cannot be empty"
            )

        # Existing query_log.intent is VARCHAR(100).
        # Store compact multi-intent information.
        intent_value = json.dumps(
            intents,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        if len(intent_value) > 100:
            raise ValueError(
                "Intent value exceeds query_log limit"
            )

        try:
            session = await self._require_session(
                session_id,
                user_id,
            )

            user_record = (
                await self.history_repo.add_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="user",
                    content=user_message,
                )
            )

            assistant_record = (
                await self.history_repo.add_message(
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    content=assistant_message,
                )
            )
            
            if assistant_record is not None:
                assistant_record.response_payload = response_payload

            query_record = (
                await self.query_log_repo.create_query_log(
                    session_id=session_id,
                    user_id=user_id,
                    query_text=user_message,
                    intent=intent_value,
                    status="completed",
                    latency_ms=latency_ms,
                )
            )

            if (
                user_record is None
                or assistant_record is None
                or query_record is None
            ):
                raise SessionNotFoundError(
                    "Session not found"
                )

            session.last_activity_at = datetime.now(
                timezone.utc
            )

            await self.db.commit()

            return {
                "user_message_id": str(user_record.id),
                "assistant_message_id": str(
                    assistant_record.id
                ),
                "query_log_id": str(query_record.id),
            }

        except Exception:
            await self.db.rollback()
            raise

    # SESSION UTILIY

    async def get_latest_session(self, user_id: str):

        user_id = self._validate_user(user_id)

        statement = (
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.status == "active",
            )
            .order_by(
                ChatSession.created_at.desc(),
                ChatSession.id.desc(),
            )
            .limit(1)
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def get_session_history(
        self,
        session_id: UUID,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ):
        user_id = self._validate_user(user_id)

        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")

        if offset < 0:
            raise ValueError("Offset cannot be negative")

        session = await self._require_session(
            session_id=session_id,
            user_id=user_id,
        )

        statement = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(
                ChatMessage.created_at.asc(),
                ChatMessage.id.asc(),
            )
            .limit(limit + 1)
            .offset(offset)
        )

        result = await self.db.execute(statement)
        rows = result.scalars().all()

        return {
            "session": session,
            "messages": rows[:limit],
            "has_more": len(rows) > limit,
        }

    async def resume_session(
        self,
        session_id: UUID,
        user_id: str,
    ):
        user_id = self._validate_user(user_id)

        try:
            statement = (
                select(ChatSession)
                .where(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id,
                )
                .with_for_update()
            )

            result = await self.db.execute(statement)
            session = result.scalar_one_or_none()

            if session is None:
                raise SessionNotFoundError(
                    "Session not found"
                )

            if session.status != "active":
                raise ValueError(
                    "This session cannot be resumed"
                )

            session.last_activity_at = datetime.now(
                timezone.utc
            )

            await self.db.commit()
            await self.db.refresh(session)

            return session

        except Exception:
            await self.db.rollback()
            raise