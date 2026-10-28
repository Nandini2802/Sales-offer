
"""
Repository for chatbot conversation history.

Responsibilities:
    - Save user and assistant messages
    - Retrieve messages for user-owned sessions
    - Retrieve recent conversation context
    - Count messages in a session
    - Update parent session activity timestamp

All message access is scoped through ChatSession.user_id.

Transaction commit/rollback belongs to the service layer.
"""

import uuid

from sqlalchemy import (
    func,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    ChatMessage,
    ChatSession,
)


class ChatHistoryRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _session_belongs_to_user(
        self,
        session_id: uuid.UUID,
        user_id: str,
    ) -> bool:
        """
        Check whether a session belongs to the user.
        """

        statement = select(ChatSession.id).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none() is not None

    async def add_message(
        self,
        session_id: uuid.UUID,
        user_id: str,
        role: str,
        content: str,
    ) -> ChatMessage | None:
        """
        Save a message to a user-owned session.

        Returns None if the session is inaccessible.

        Caller must commit the transaction.
        """

        if role not in ("user", "assistant"):
            raise ValueError(
                "role must be 'user' or 'assistant'"
            )

        if not content or not content.strip():
            raise ValueError(
                "Message content cannot be empty"
            )

        # Lock the parent session during insertion.
        # This also serializes activity timestamp updates.
        ownership_statement = (
            select(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
            .with_for_update()
        )

        result = await self.db.execute(
            ownership_statement
        )

        parent_session = result.scalar_one_or_none()

        if parent_session is None:
            return None

        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
        )

        self.db.add(message)

        # Persist pending message before returning.
        await self.db.flush()

        # Keep session listing ordered by recent activity.
        parent_session.updated_at = func.now()

        await self.db.flush()

        return message

    async def get_message(
        self,
        message_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: str,
    ) -> ChatMessage | None:
        """
        Retrieve a message from a user-owned session.
        """

        statement = (
            select(ChatMessage)
            .join(
                ChatSession,
                ChatMessage.session_id == ChatSession.id,
            )
            .where(
                ChatMessage.id == message_id,
                ChatMessage.session_id == session_id,
                ChatSession.user_id == user_id,
            )
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def list_messages(
        self,
        session_id: uuid.UUID,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatMessage]:
        """
        Retrieve messages in chronological order.

        Returns an empty list if the session
        does not exist or belongs to another user.
        """

        if not 1 <= limit <= 100:
            raise ValueError(
                "limit must be between 1 and 100"
            )

        if offset < 0:
            raise ValueError(
                "offset cannot be negative"
            )

        statement = (
            select(ChatMessage)
            .join(
                ChatSession,
                ChatMessage.session_id == ChatSession.id,
            )
            .where(
                ChatMessage.session_id == session_id,
                ChatSession.user_id == user_id,
            )
            .order_by(
                ChatMessage.created_at.asc(),
                ChatMessage.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def get_recent_messages(
        self,
        session_id: uuid.UUID,
        user_id: str,
        limit: int = 10,
    ) -> list[ChatMessage]:
        """
        Retrieve the latest N messages.

        Returns messages in chronological order,
        suitable for building conversation context.
        """

        if not 1 <= limit <= 100:
            raise ValueError(
                "limit must be between 1 and 100"
            )

        statement = (
            select(ChatMessage)
            .join(
                ChatSession,
                ChatMessage.session_id == ChatSession.id,
            )
            .where(
                ChatMessage.session_id == session_id,
                ChatSession.user_id == user_id,
            )
            .order_by(
                ChatMessage.created_at.desc(),
                ChatMessage.id.desc(),
            )
            .limit(limit)
        )

        result = await self.db.execute(statement)

        messages = list(result.scalars().all())

        # Reverse to provide oldest -> newest context.
        messages.reverse()

        return messages

    async def count_messages(
        self,
        session_id: uuid.UUID,
        user_id: str,
    ) -> int:
        """
        Count messages in a user-owned session.
        """

        statement = (
            select(func.count(ChatMessage.id))
            .join(
                ChatSession,
                ChatMessage.session_id == ChatSession.id,
            )
            .where(
                ChatMessage.session_id == session_id,
                ChatSession.user_id == user_id,
            )
        )

        result = await self.db.execute(statement)

        return result.scalar_one()
