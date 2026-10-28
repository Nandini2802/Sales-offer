
import logging

from app.services.api_cache_service import APICacheService
from app.persistence.redis_store import RedisCacheKeys

logger = logging.getLogger(__name__)


class ProjectCatalogService:

    def __init__(self, redis_client):
        self.cache = APICacheService(redis_client)

    async def get_project_names(self) -> list[str]:

        cached = await self.cache.get(
            RedisCacheKeys.MARKETING_CATALOG
        )

        if not isinstance(cached, dict):
            logger.warning("MARKETING_CATALOG_NOT_FOUND")
            return []

        # Handle the cached response structure.
        data = cached.get("data", {})

        if not isinstance(data, dict):
            return []

        # Some cache wrappers store the original
        # API response inside another data object.
        if (
            "marketingCollateral" not in data
            and isinstance(data.get("data"), dict)
        ):
            data = data["data"]

        projects = data.get(
            "marketingCollateral", []
        )

        names = {
            item["project_title"].strip()
            for item in projects
            if isinstance(item, dict)
            and isinstance(item.get("project_title"), str)
            and item["project_title"].strip()
        }

        result = sorted(names)

        logger.info(
            "PROJECT_CATALOG_LOADED | count=%s",
            len(result),
        )

        return result
