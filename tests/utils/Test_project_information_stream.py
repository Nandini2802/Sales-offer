
import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from app.schemas.generation import GenerationResult

load_dotenv()

PROMPT_PATH = (
    Path("app/prompts")
    / "generation_project_information_v1.md"
)


async def main():
    client = AsyncOpenAI(
        api_key=os.environ["FOUNDRY_OPENAI_API_KEY"],
        base_url=os.environ["FOUNDRY_OPENAI_BASE_URL"],
    )

    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    # Mock verified project information for this test.
    # These are test values, NOT actual Danube project facts.
    service_results = {
        "service": "project_information",
        "project": "Demo Residence",
        "project_details": {
            "location": "Dubai",
            "description": "A sample residential project",
            "unit_types": ["Studio", "1 Bedroom", "2 Bedroom"],
        },
    }

    payload = {
        "user_message": "Tell me about Demo Residence",
        "detected_language": "en",
        "detected_intents": ["project_information"],
        "verified_service_results": service_results,
        "recent_conversation": [],
    }

    print("\nAssistant (streaming raw JSON):\n")

    start = time.perf_counter()

    async with client.responses.stream(
        model=os.environ["FOUNDRY_OPENAI_MODEL"],
        instructions=prompt,
        input=json.dumps(payload, ensure_ascii=False),
        text_format=GenerationResult,
    ) as stream:

        async for event in stream:
            if event.type == "response.output_text.delta":
                print(event.delta, end="", flush=True)

        final_response = await stream.get_final_response()

    result = final_response.output_parsed

    if result is None:
        raise RuntimeError("Structured generation failed")

    print("\n\n--- VALIDATED RESULT ---")
    print("Response:", result.response)
    print("Followups:", result.followups)

    print(
        f"\nTotal time: "
        f"{time.perf_counter() - start:.2f}s"
    )


if __name__ == "__main__":
    asyncio.run(main())
