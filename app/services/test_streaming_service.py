
import os
import uuid

from openai import AsyncOpenAI
from app.utils.sse import format_sse


async def test_stream_chat(message: str):
    session_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    yield format_sse("session", {
        "session_id": session_id,
        "correlation_id": correlation_id,
    })

    client = AsyncOpenAI(
        api_key=os.environ["FOUNDRY_OPENAI_API_KEY"],
        base_url=os.environ["FOUNDRY_OPENAI_BASE_URL"],
    )

    response_text = ""

    try:
        stream = await client.responses.create(
            model=os.environ["FOUNDRY_OPENAI_MODEL"],
            instructions=(
                "You are a demo real estate assistant. "
                "Answer briefly. Do not invent property "
                "prices, availability or project facts."
            ),
            input=message,
            stream=True,
        )

        async for event in stream:
            if event.type == "response.output_text.delta":
                delta = event.delta
                response_text += delta

                yield format_sse("token", {
                    "text": delta,
                })

        followups = [
            "Show available projects",
            "Show project brochures",
            "Show available units",
        ]

        yield format_sse("followups", {
            "followups": followups,
        })

        yield format_sse("final", {
            "session_id": session_id,
            "response": response_text,
            "followups": followups,
        })

        yield format_sse("done", {
            "status": "completed",
        })

    except Exception:
        yield format_sse("error", {
            "error": {
                "code": "STREAMING_TEST_ERROR",
                "message": "Streaming test failed.",
                "session_id": session_id,
                "correlation_id": correlation_id,
                "retryable": True,
            }
        })

        yield format_sse("done", {
            "status": "failed",
        })
