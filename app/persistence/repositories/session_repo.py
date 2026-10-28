
"""
Repository for chatbot session database operations.

Responsibilities:
    - Create chatbot sessions
    - Retrieve user-owned sessions
    - List sessions belonging to a user
    - Update session metadata
    - Delete user-owned sessions

All existing-session operations enforce user ownership.

Transaction commit/rollback is handled by the service layer.
"""

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import ChatSession


class SessionRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self,
        user_id: str,
        user_role: str,
        source: str | None = None,
        app_source: str | None = None,
        title: str | None = None,
    ) -> ChatSession:
        """
        Create a new chatbot conversation.

        The caller is responsible for committing.
        """

        session = ChatSession(
            user_id=user_id,
            user_role=user_role,
            source=source,
            app_source=app_source,
            title=title,
        )

        self.db.add(session)

        await self.db.flush()

        return session

    async def get_session(
        self,
        session_id: uuid.UUID,
        user_id: str,
    ) -> ChatSession | None:
        """
        Retrieve a session only if it belongs to the user.
        """

        statement = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChatSession]:
        """
        List a user's sessions, newest updated first.
        """

        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        if offset < 0:
            raise ValueError("offset cannot be negative")

        statement = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(
                ChatSession.updated_at.desc(),
                ChatSession.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def count_sessions(
        self,
        user_id: str,
    ) -> int:
        """
        Count sessions belonging to a user.
        """

        statement = (
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.user_id == user_id)
        )

        result = await self.db.execute(statement)

        return result.scalar_one()

    async def update_session(
        self,
        session_id: uuid.UUID,
        user_id: str,
        title: str | None = None,
    ) -> ChatSession | None:
        """
        Update the title of a user-owned session.

        Returns None when the session does not exist
        or does not belong to the user.
        """

        session = await self.get_session(
            session_id=session_id,
            user_id=user_id,
        )

        if session is None:
            return None

        session.title = title
        session.updated_at = func.now()

        await self.db.flush()

        return session

    async def delete_session(
        self,
        session_id: uuid.UUID,
        user_id: str,
    ) -> bool:
        """
        Delete a session only if owned by the user.

        Related messages and query logs are deleted
        through the configured ORM cascade.

        The caller is responsible for committing.
        """

        session = await self.get_session(
            session_id=session_id,
            user_id=user_id,
        )

        if session is None:
            return False

        await self.db.delete(session)
        await self.db.flush()

        return True
