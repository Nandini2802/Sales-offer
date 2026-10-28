import asyncio

from app.core.config import get_settings
from app.core.keyvault import load_application_secrets
from openai import AsyncOpenAI

from app.services.router_service import RouterService


async def main():

    settings = get_settings()
    secrets = await load_application_secrets()

    client = AsyncOpenAI(
        base_url=settings.foundry_openai_base_url,
        api_key=(
            secrets.foundry_openai_api_key
            .get_secret_value()
        ),
    )

    try:
        router = RouterService(
            client=client,
            model=settings.foundry_openai_model,
        )

        result = await router.classify(
            "Give me amenities, "
            "I want to generate sales offer, "
            "How many units are available under 1 million AED"
        )

        print(result.model_dump_json(indent=2))

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())