import json
import uuid
from typing import Any

from redis.asyncio import Redis


CONTEXT_TTL_SECONDS = 6 * 60 * 60
MAX_HISTORY_MESSAGES = 12


class SessionNotFound(Exception):
    pass


class SessionAccessDenied(Exception):
    pass


class ConversationContextService:

    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    @staticmethod
    def _key(session_id: uuid.UUID) -> str:
        return f"danube:chat:context:{session_id}"

    async def create_session(
        self,
        session_id: uuid.UUID,
        user_id: str,
    ) -> dict[str, Any]:

        context = {
            "session_id": str(session_id),
            "user_id": user_id,
            "history": [],
            "current_project": None,
            "pending": None,
        }

        created = await self.redis.set(
            self._key(session_id),
            json.dumps(context),
            ex=CONTEXT_TTL_SECONDS,
            nx=True,
        )

        if not created:
            raise RuntimeError("Session already exists")

        return context

    async def get_session(
        self,
        session_id: uuid.UUID,
        user_id: str,
    ) -> dict[str, Any]:

        raw = await self.redis.get(
            self._key(session_id)
        )

        if raw is None:
            raise SessionNotFound(
                "Session not found or expired"
            )

        context = json.loads(raw)

        if context.get("user_id") != user_id:
            raise SessionAccessDenied(
                "Session does not belong to this user"
            )

        return context

    async def save_session(
        self,
        context: dict[str, Any],
    ) -> None:

        key = self._key(
            uuid.UUID(context["session_id"])
        )

        # Only update existing sessions.
        # Avoid recreating expired sessions.
        saved = await self.redis.set(
            key,
            json.dumps(context),
            ex=CONTEXT_TTL_SECONDS,
            xx=True,
        )

        if not saved:
            raise SessionNotFound(
                "Session expired before saving"
            )

    @staticmethod
    def add_exchange(
        context: dict[str, Any],
        user_message: str,
        assistant_message: str,
    ) -> None:

        history = context.setdefault(
            "history", []
        )

        history.extend([
            {
                "role": "user",
                "content": user_message,
            },
            {
                "role": "assistant",
                "content": assistant_message,
            },
        ])

        context["history"] = history[
            -MAX_HISTORY_MESSAGES:
        ]

    @staticmethod
    def set_pending(
        context: dict[str, Any],
        intent: str,
        asset_types: list[str],
        missing_field: str,
    ) -> None:

        context["pending"] = {
            "intent": intent,
            "asset_types": asset_types,
            "missing_field": missing_field,
        }

    @staticmethod
    def clear_pending(
        context: dict[str, Any],
    ) -> None:
        context["pending"] = None
