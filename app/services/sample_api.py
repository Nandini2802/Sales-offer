import httpx

from app.core.config import settings
from app.utils.retry import with_retry


@with_retry(
    attempts=3,
    exceptions=(httpx.RequestError,),
)
async def call_sample_api():

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds
    ) as client:

        response = await client.get(
            "https://jsonplaceholder.typicode.com/todos/1"
        )

        response.raise_for_status()

        return response.json()