import asyncio
import httpx

from app.utils.retry import with_retry


attempt_count = 0

@with_retry(
    attempts=3,
    min_wait=1,
    max_wait=4,
    exceptions=(httpx.RequestError,),
)
async def simulate_api_failure():
    global attempt_count
    attempt_count += 1

    print(f"API attempt: {attempt_count}")

    raise httpx.ConnectError("Simulated connection failure")


async def main():
    try:
        await simulate_api_failure()

    except httpx.RequestError as e:
        print(f"All retries exhausted: {e}")


if __name__ == "__main__":
    asyncio.run(main())