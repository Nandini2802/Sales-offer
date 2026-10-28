
import asyncio

from app.core.keyvault import load_application_secrets
from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.services.api_cache_service import (
    get_cached_marketing_data,
)


async def main():

    clients = None

    try:
        secrets = await load_application_secrets()

        clients = await create_service_clients(secrets)

        marketing_data = await get_cached_marketing_data(
            clients.redis
        )

        if marketing_data is None:
            print("CACHE MISS: Marketing data not available")
            return

        print("DATA SOURCE: REDIS")
        print("DATA TYPE:", type(marketing_data).__name__)

        if isinstance(marketing_data, dict):
            print(
                "TOP LEVEL FIELDS:",
                list(marketing_data.keys()),
            )

        elif isinstance(marketing_data, list):
            print(
                "TOTAL RECORDS:",
                len(marketing_data),
            )

    finally:
        if clients is not None:
            await close_service_clients(clients)


if __name__ == "__main__":
    asyncio.run(main())
