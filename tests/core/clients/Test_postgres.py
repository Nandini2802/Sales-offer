import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

async def main():
    url = os.getenv("POSTGRES_URL")

    if not url:
        raise ValueError("POSTGRES_URL is missing")

    engine = create_async_engine(url, pool_pre_ping=True)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT current_database(), current_user")
            )

            database, user = result.one()

            print("PostgreSQL connected successfully!")
            print("Database:", database)
            print("User:", user)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())