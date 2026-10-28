
import os
import pytest

from openai import AsyncOpenAI
from dotenv import load_dotenv

from app.services.generation_service import (
    GenerationService,
)

load_dotenv()

@pytest.mark.asyncio
async def test_marketing_generation_live():

    client = AsyncOpenAI(
        base_url=os.environ[
            "FOUNDRY_OPENAI_BASE_URL"
        ],
        api_key=os.environ[
            "FOUNDRY_OPENAI_API_KEY"
        ],
    )

    try:
        service = GenerationService(
            client=client,
            model=os.getenv(
                "GENERATION_OPENAI_MODEL",
                "gpt-5.4",
            ),
        )

        result = await service.generate(
            message="Give me Greenz floor plans",
            language="English",
            intents=["marketing"],
            service_results={
                "service": "marketing",
                "project": "Greenz",
                "requested_asset_types": [
                    "floor_plan"
                ],
                "assets_found": True,
                "asset_count": 1,
                "available_assets": [
                    {
                        "name": "Greenz Floor Plans",
                        "type": "floor_plan",
                        "format": "zip",
                    }
                ],
                "verified_project_details": {},
            },
            history=[],
        )

        print("\nGenerated response:")
        print(result.response)

        print("\nFollow-up chips:")
        for chip in result.followups:
            print("-", chip)

        assert result.response.strip()
        assert len(result.followups) <= 3
        assert "Greenz" in result.response

    finally:
        await client.close()
