
import asyncio
import json
import os
import time

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field


load_dotenv()


# Same basic structure as your Danube GenerationResult
class GenerationResult(BaseModel):
    response: str
    followups: list[str] = Field(min_length=3, max_length=3)


class ResponseExtractor:
    """
    Demo-only incremental JSON parser.

    Assumes the model generates:
    {"response": "...", "followups": [...]}

    Extracts the response string as it arrives.
    """

    def __init__(self):
        self.buffer = ""
        self.started = False
        self.finished = False
        self.escaped = False
        self.escape_buffer = ""

    def feed(self, chunk: str) -> str:
        if self.finished:
            return ""

        self.buffer += chunk
        output = []

        if not self.started:
            import re

            match = re.match(
                r'\s*\{\s*"response"\s*:\s*"',
                self.buffer,
            )

            if match is None:
                return ""

            self.buffer = self.buffer[match.end():]
            self.started = True

        i = 0

        while i < len(self.buffer):
            char = self.buffer[i]

            if self.escaped:
                self.escape_buffer += char

                if self.escape_buffer.startswith("u"):
                    if len(self.escape_buffer) < 5:
                        i += 1
                        continue

                decoded = json.loads(
                    '"\\' + self.escape_buffer + '"'
                )
                output.append(decoded)

                self.escaped = False
                self.escape_buffer = ""

            elif char == "\\":
                self.escaped = True
                self.escape_buffer = ""

            elif char == '"':
                self.finished = True
                i += 1
                break

            else:
                output.append(char)

            i += 1

        self.buffer = self.buffer[i:]
        return "".join(output)


async def main():

    client = AsyncOpenAI(
        api_key=os.environ["FOUNDRY_OPENAI_API_KEY"],
        base_url=os.environ["FOUNDRY_OPENAI_ENDPOINT"],
    )

    model = os.environ["FOUNDRY_OPENAI_MODEL"]

    extractor = ResponseExtractor()

    start_time = time.perf_counter()
    first_text_time = None

    async with client.responses.stream(
        model=model,
        instructions=(
            "You are a Danube Properties chatbot assistant. "
            "Return a structured response containing two fields: "
            "response and followups. "
            "Write approximately 100 words in response. "
            "Generate exactly 3 short follow-up questions. "
            "Put the response field first."
        ),
        input="Tell me about Danube Properties.",
        text_format=GenerationResult,
    ) as stream:

        async for event in stream:

            if event.type == "response.output_text.delta":

                text = extractor.feed(event.delta)

                if text:

                    if first_text_time is None:
                        first_text_time = (
                            time.perf_counter() - start_time
                        )


        final_response = await stream.get_final_response()

        result = final_response.output_parsed

    if result is None:
        raise RuntimeError(
            "Model returned no validated structured response."
        )

    if not extractor.finished:
        raise RuntimeError(
            "The response field was not fully streamed."
        )


if __name__ == "__main__":
    asyncio.run(main())
