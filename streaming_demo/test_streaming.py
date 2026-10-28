import asyncio
import os
import time

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


async def main():
    client = AsyncOpenAI(
        api_key=os.environ["FOUNDRY_OPENAI_API_KEY"],
        base_url=os.environ["FOUNDRY_OPENAI_ENDPOINT"],
    )

    start = time.perf_counter()
    first_token_time = None

    stream = await client.responses.create(
        model=os.environ["FOUNDRY_OPENAI_MODEL"],
        input=(
            "Explain what Danube Properties does "
            "in approximately 150 words."
        ),
        stream=True,
    )

    async for event in stream:
        if event.type == "response.output_text.delta":
            if first_token_time is None:
                first_token_time = time.perf_counter() - start


if __name__ == "__main__":
    asyncio.run(main())