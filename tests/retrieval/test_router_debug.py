
import json
import pytest

from main import app
from app.schemas.routing import RoutingResult
from app.services.router_service import RouterService
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_router_classification():
    settings = get_settings()

    # Initialize app lifespan and its service clients
    async with app.router.lifespan_context(app):
        clients = app.state.clients

        # Display schema without printing credentials
        schema = RoutingResult.model_json_schema()

        print(
            "\nROUTING SCHEMA:\n",
            json.dumps(schema, indent=2, default=str),
        )

        router = RouterService(
            client=clients.foundry_openai,
            model=settings.foundry_openai_model,
        )

        result = await router.classify(
            message="Show me 2 bedroom units",
            history=[],
            available_projects=["TEST PROJECT"],
            inventory_active_projects=["TEST PROJECT"],
            inventory_unit_projects=["TEST PROJECT"],
        )

        print("\nROUTER RESULT:")
        print(result.model_dump_json(indent=2))

        assert result.intents
        assert result.intents[0].intent == "inventory"
        assert result.intents[0].bedrooms == 2
