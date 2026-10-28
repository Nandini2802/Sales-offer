
"""
Integration test for centralized service clients.
"""

import asyncio
import logging

from sqlalchemy import text

from app.core.clients import (
    create_service_clients,
    close_service_clients,
)


logging.basicConfig(level=logging.INFO)


async def test_clients():

    clients = None

    try:
        print("\nInitializing service clients...\n")

        clients = await create_service_clients()

        print("Service clients initialized successfully")

        # PostgreSQL test
        async with clients.postgres.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar_one() == 1

        print("PostgreSQL connection: PASSED")

        # Redis test
        assert await clients.redis.ping()

        print("Redis connection: PASSED")

        # Pinecone test
        stats = await asyncio.to_thread(
            clients.pinecone_index.describe_index_stats
        )

        assert stats is not None

        print("Pinecone connection: PASSED")

    except Exception as exc:

        print(f"\nClient test FAILED: {type(exc).__name__}: {exc}")
        raise

    finally:

        if clients is not None:
            await close_service_clients(clients)

        print("\nTest completed. Resources cleaned up.")


if __name__ == "__main__":
    asyncio.run(test_clients())
