
import asyncio

from app.core.keyvault import load_application_secrets
from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.services.api_cache_service import APICacheService
from app.persistence.redis_store import RedisCacheKeys


async def main():

    clients = None

    try:
        # Step 1: Load secrets
        secrets = await load_application_secrets()

        # Step 2: Connect to Redis
        clients = await create_service_clients(secrets)

        # Step 3: Initialize cache service
        cache = APICacheService(clients.redis)

        # Step 4: Retrieve cached Marketing API data
        cached = await cache.get(
            RedisCacheKeys.MARKETING_CATALOG
        )

        if cached is None:
            print("CACHE MISS: Marketing data not found")
            return

        print("CACHE HIT: Marketing data found")

        print(
            "Last refreshed:",
            cached.get("refreshed_at"),
        )

        marketing_data = cached.get("data")

        print(
            "Data type:",
            type(marketing_data).__name__,
        )

        if isinstance(marketing_data, list):
            print(
                "Total records:",
                len(marketing_data),
            )

        elif isinstance(marketing_data, dict):
            print(
                "Top-level fields:",
                list(marketing_data.keys()),
            )

        # Step 5: Check remaining expiry time
        ttl = await clients.redis.ttl(
            RedisCacheKeys.MARKETING_CATALOG
        )

        print(
            "Remaining TTL (seconds):",
            ttl,
        )

    finally:
        if clients is not None:
            await close_service_clients(clients)


if __name__ == "__main__":
    asyncio.run(main())
