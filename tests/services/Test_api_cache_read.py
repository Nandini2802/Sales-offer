
import asyncio
from datetime import datetime, timezone

from app.core.keyvault import load_application_secrets
from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.persistence.redis_store import RedisCacheKeys
from app.services.api_cache_service import APICacheService


async def main():
    secrets = await load_application_secrets()
    clients = await create_service_clients(secrets)

    try:
        cache = APICacheService(clients.redis)

        cache_keys = {
            "Marketing API": RedisCacheKeys.MARKETING_CATALOG,
            "Currency Rate API": RedisCacheKeys.CURRENCY_RATES,
        }

        for api_name, key in cache_keys.items():
            print(f"\n--- {api_name} ---")

            cached = await cache.get(key)
            ttl = await clients.redis.ttl(key)

            if cached is None:
                print("STATUS: CACHE MISS")
                continue

            print("STATUS: CACHE HIT")
            print("LAST REFRESHED:", cached.get("refreshed_at"))
            print("REMAINING TTL:", ttl, "seconds")

            data = cached.get("data")

            print("DATA TYPE:", type(data).__name__)

            if isinstance(data, dict):
                print("TOP LEVEL FIELDS:", list(data.keys()))

            elif isinstance(data, list):
                print("TOTAL RECORDS:", len(data))

    finally:
        await close_service_clients(clients)


if __name__ == "__main__":
    asyncio.run(main())
