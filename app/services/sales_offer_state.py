
import json

from app.core.config import get_settings


class SalesOfferState:

    def __init__(self, redis_client):
        self.redis = redis_client
        self.settings = get_settings()

    @staticmethod
    def key(user_id: str, session_id: str) -> str:
        return f"danube:sales-offer:pending:{user_id}:{session_id}"

    async def save(
        self,
        *,
        user_id: str,
        session_id: str,
        state: dict,
    ):
        await self.redis.set(
            self.key(user_id, session_id),
            json.dumps(state),
            ex=self.settings.sales_offer_selection_ttl_seconds,
        )

    async def load(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> dict | None:

        raw = await self.redis.get(
            self.key(user_id, session_id)
        )

        if not raw:
            return None

        return json.loads(raw)

    async def clear(
        self,
        *,
        user_id: str,
        session_id: str,
    ):
        await self.redis.delete(
            self.key(user_id, session_id)
        )
