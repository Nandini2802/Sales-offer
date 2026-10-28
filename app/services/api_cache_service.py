import json
import logging
from typing import Any

from app.persistence.redis_store import RedisCacheKeys


logger = logging.getLogger(__name__)


class APICacheService:
    """
    Stores and retrieves API responses in Redis.
    """

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get(self, key: str) -> Any | None:
        """
        Retrieve cached data from Redis.
        Returns None if the key does not exist.
        """

        cached_data = await self.redis.get(key)

        if cached_data is None:
            logger.info(
                "API_CACHE_MISS | key=%s",
                key,
            )
            return None

        logger.info(
            "API_CACHE_HIT | key=%s",
            key,
        )

        return json.loads(cached_data)

    async def set(
        self,
        key: str,
        data: Any,
        ttl_seconds: int,
    ) -> None:
        """
        Store JSON data in Redis with an expiry.
        """

        serialized_data = json.dumps(
            data,
            ensure_ascii=False,
        )

        await self.redis.set(
            key,
            serialized_data,
            ex=ttl_seconds,
        )

        logger.info(
            "API_CACHE_UPDATED | key=%s | ttl=%s",
            key,
            ttl_seconds,
        )

    async def delete(self, key: str) -> bool:
        """
        Remove a cached value from Redis.
        """

        deleted = await self.redis.delete(key)

        logger.info(
            "API_CACHE_DELETED | key=%s | deleted=%s",
            key,
            bool(deleted),
        )

        return bool(deleted)


async def get_cached_marketing_data(redis_client):
    """
    Retrieve Marketing API data from Redis only.

    Does not call the external Marketing API.
    """

    cache = APICacheService(redis_client)

    cached_response = await cache.get(
        RedisCacheKeys.MARKETING_CATALOG
    )

    if cached_response is None:
        logger.warning(
            "MARKETING_DATA_CACHE_MISS"
        )
        return None

    logger.info(
        "MARKETING_DATA_SOURCE | source=redis"
    )

    return cached_response["data"]


async def get_cached_currency_data(redis_client):
    cache = APICacheService(redis_client)

    cached_response = await cache.get(
        RedisCacheKeys.CURRENCY_RATES
    )

    if cached_response is None:
        logger.warning("CURRENCY_DATA_CACHE_MISS")
        return None

    logger.info(
        "CURRENCY_DATA_SOURCE | source=redis"
    )

    return (
        cached_response.get("data")
        if isinstance(cached_response, dict)
        else None
    )