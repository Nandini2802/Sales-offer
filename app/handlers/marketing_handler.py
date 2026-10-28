from app.schemas.handler_result import HandlerResult
from app.services.marketing_service import MarketingService
from app.services.template_service import TemplateService


class MarketingHandler:

    def __init__(self, redis_client):
        self.marketing_service = MarketingService(
            redis_client
        )
        self.template_service = TemplateService()

    async def handle(self, intent) -> HandlerResult:

        result = HandlerResult(intent="marketing")

        # 1. CHECK PROJECT NAME

        project_name = intent.project_name

        if not project_name:
            result.messages.append(
                "Which Danube project would you like "
                "the marketing materials for?"
            )
            return result

        # 2. CHECK REQUESTED ASSET TYPES

        asset_types = intent.marketing_assets or []

        if not asset_types:
            result.messages.append(
                f"Which marketing materials would you "
                f"like for {project_name} — brochures, "
                "videos, floor plans, images, or all "
                "marketing materials?"
            )
            return result

        # 3. FETCH ASSETS FROM REDIS

        assets = await self.marketing_service.get_assets(
            project_name=project_name,
            asset_types=asset_types,
        )

        if not assets:
            result.messages.append(
                "No requested marketing materials "
                f"were found for {project_name}."
            )
            return result

        # 4. PREPARE VERIFIED ASSET DATA

        asset_summary = []

        for asset in assets:

            asset_summary.append(
                {
                    "project": asset.project,
                    "asset_type": asset.asset_type,
                    "file_count": len(asset.files),
                    "has_zip": bool(asset.zip_url),
                    "file_names": [
                        file.name
                        for file in asset.files
                    ],
                }
            )

            # 5. RENDER HTML CARD

            html_content = (
                self.template_service.render_marketing_asset(
                    asset
                )
            )

            result.html_blocks.append(
                {
                    "card_type": asset.asset_type,
                    "html": html_content,
                }
            )

            # 6. PREPARE FILE METADATA

            for file in asset.files:
                result.files.append(
                    {
                        "name": file.name,
                        "type": asset.asset_type,
                        "download_url": file.download_url,
                        "file_size_bytes": (
                            file.file_size_bytes
                        ),
                    }
                )

            # 7. ADD ZIP FILE IF AVAILABLE

            if asset.zip_url:
                result.files.append(
                    {
                        "name": (
                            f"{asset.project} "
                            f"{asset.asset_type} ZIP"
                        ),
                        "type": asset.asset_type,
                        "format": "zip",
                        "download_url": asset.zip_url,
                    }
                )

        # 8. PREPARE CONTEXT FOR LLM 2

        result.generation_context = {
            "service": "marketing",
            "project": project_name,
            "assets_found": True,
            "available_assets": asset_summary,
        }

        result.has_data = bool(asset_summary)

        return result
