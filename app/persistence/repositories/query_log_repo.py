"""
Repository for chatbot query logs.

Responsibilities:
    - Create query logs
    - Retrieve user-owned query logs
    - List query logs for a user or session
    - Count user-owned query logs

Query logs are append-only in Phase 1.

The service layer handles transaction commits.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    ChatSession,
    QueryLog,
)


class QueryLogRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_query_log(
        self,
        session_id: uuid.UUID,
        user_id: str,
        query_text: str,
        intent: str | None = None,
        status: str = "pending",
        latency_ms: int | None = None,
    ) -> QueryLog | None:
        """
        Insert a query log for a user-owned session.

        Returns None if the session is inaccessible.
        Does not commit the transaction.
        """

        if not query_text or not query_text.strip():
            raise ValueError(
                "query_text cannot be empty"
            )

        if not status or not status.strip():
            raise ValueError(
                "status cannot be empty"
            )

        if latency_ms is not None and latency_ms < 0:
            raise ValueError(
                "latency_ms cannot be negative"
            )

        if len(status) > 30:
            raise ValueError(
                "status cannot exceed 30 characters"
            )

        if intent is not None and len(intent) > 100:
            raise ValueError(
                "intent cannot exceed 100 characters"
            )

        # Lock the parent row to prevent concurrent
        # deletion during this insert.
        statement = (
            select(ChatSession.id)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
            .with_for_update(key_share=True)
        )

        result = await self.db.execute(statement)

        if result.scalar_one_or_none() is None:
            return None

        query_log = QueryLog(
            session_id=session_id,
            user_id=user_id,
            query_text=query_text,
            intent=intent,
            status=status,
            latency_ms=latency_ms,
        )

        self.db.add(query_log)

        await self.db.flush()

        return query_log

    async def get_query_log(
        self,
        log_id: uuid.UUID,
        user_id: str,
    ) -> QueryLog | None:
        """
        Retrieve a log belonging to the user.

        Verify both the log user_id and
        parent session ownership.
        """

        statement = (
            select(QueryLog)
            .join(
                ChatSession,
                QueryLog.session_id == ChatSession.id,
            )
            .where(
                QueryLog.id == log_id,
                QueryLog.user_id == user_id,
                ChatSession.user_id == user_id,
            )
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def list_query_logs(
        self,
        user_id: str,
        session_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[QueryLog]:
        """
        List logs belonging to a user.

        Optionally filter by session_id.
        Newest logs are returned first.
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
            select(QueryLog)
            .join(
                ChatSession,
                QueryLog.session_id == ChatSession.id,
            )
            .where(
                QueryLog.user_id == user_id,
                ChatSession.user_id == user_id,
            )
        )

        if session_id is not None:
            statement = statement.where(
                QueryLog.session_id == session_id
            )

        statement = (
            statement
            .order_by(
                QueryLog.created_at.desc(),
                QueryLog.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def count_query_logs(
        self,
        user_id: str,
        session_id: uuid.UUID | None = None,
    ) -> int:
        """
        Count logs belonging to a user.
        """

        statement = (
            select(func.count(QueryLog.id))
            .join(
                ChatSession,
                QueryLog.session_id == ChatSession.id,
            )
            .where(
                QueryLog.user_id == user_id,
                ChatSession.user_id == user_id,
            )
        )

        if session_id is not None:
            statement = statement.where(
                QueryLog.session_id == session_id
            )

        result = await self.db.execute(statement)

        return result.scalar_one()
