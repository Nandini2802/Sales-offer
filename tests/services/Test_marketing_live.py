import pytest

from app.core.keyvault import load_application_secrets
from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.services.marketing_service import MarketingService
from app.services.template_service import TemplateService


@pytest.mark.asyncio
async def test_greenz_marketing_assets():

    secrets = await load_application_secrets()
    clients = await create_service_clients(secrets)

    try:
        marketing = MarketingService(clients.redis)
        templates = TemplateService()

        assets = await marketing.get_assets(
            project_name="Greenz",
            asset_types=[
                "brochures",
                "videos",
                "floor-plans",
                "interiors",
            ],
        )

        for asset in assets:
            html = templates.render_marketing_asset(
                asset
            )

            print(
                f"\nAsset: {asset.asset_type}"
                f"\nFiles: {asset.total_files}"
                f"\nZIP available: {bool(asset.zip_url)}"
                f"\nHTML generated: {bool(html)}"
            )

            assert html.strip()

            if asset.asset_type in {
                "brochures",
                "videos",
            }:
                assert len(asset.files) > 0

            else:
                assert asset.zip_url is not None

        assert assets, "No Greenz assets found"

    finally:
        await close_service_clients(clients)