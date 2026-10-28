import json


class DownloadAvailabilityState:

    TTL_SECONDS = 1800

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def key(user_id: str, session_id: str) -> str:
        return (
            f"danube:download-availability:"
            f"{user_id}:{session_id}"
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

        if raw is None:
            return None

        return json.loads(raw)

    async def save(
        self,
        *,
        user_id: str,
        session_id: str,
        state: dict,
    ) -> None:

        await self.redis.set(
            self.key(user_id, session_id),
            json.dumps(state),
            ex=self.TTL_SECONDS,
        )

    async def clear(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> None:

        await self.redis.delete(
            self.key(user_id, session_id)
        )