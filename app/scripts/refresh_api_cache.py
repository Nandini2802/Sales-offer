
import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.keyvault import load_application_secrets
from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.observability.app_insights import setup_application_insights
from app.retrieval.marketing_api_client import MarketingAPIClient
from app.services.api_cache_service import APICacheService
from app.persistence.redis_store import RedisCacheKeys
from app.retrieval.currency_api_client import CurrencyAPIClient



logging.getLogger("app").setLevel(logging.INFO)

logger = logging.getLogger(
    "app.scripts.refresh_api_cache"
)


async def refresh_marketing_cache(
    clients,
    secrets,
) -> bool:

    settings = get_settings()

    marketing_client = MarketingAPIClient(
        api_key=(
            secrets.marketing_api_key.get_secret_value()
        )
    )

    cache = APICacheService(
        redis_client=clients.redis
    )

    try:
        logger.info(
            "MARKETING_CACHE_REFRESH_STARTED"
        )

        # Step 1: Fetch fresh Marketing API data
        marketing_data = (
            await marketing_client.fetch_catalog()
        )

        # Validate Marketing API response before caching.

        if not isinstance(marketing_data, dict):
            raise ValueError(
                "Marketing API response must be a JSON object"
            )

        payload = marketing_data.get("data", marketing_data)

        if not isinstance(payload, dict):
            raise ValueError(
                "Invalid Marketing API data structure"
            )

        projects = payload.get("marketingCollateral")

        if (
            not isinstance(projects, list)
            or not any(
                isinstance(item, dict)
                and isinstance(item.get("project_title"), str)
                and item["project_title"].strip()
                for item in projects
            )
        ):
            raise ValueError(
                "Marketing API returned no valid projects"
            )

        # Step 2: Add refresh timestamp
        cache_payload = {
            "refreshed_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "data": marketing_data,
        }

        # Step 3: Save into Redis
        await cache.set(
            key=RedisCacheKeys.MARKETING_CATALOG,
            data=cache_payload,
            ttl_seconds=(
                settings.marketing_cache_ttl_seconds
            ),
        )

        logger.info(
            "MARKETING_CACHE_REFRESH_SUCCESS"
        )

        return True

    except Exception:
        logger.exception(
            "MARKETING_CACHE_REFRESH_FAILED"
        )

        return False


async def refresh_currency_cache(
    clients,
    secrets=None,
) -> bool:
    """
    Fetch latest currency rates and update Redis.
    """

    settings = get_settings()


    if secrets is None:
        raise ValueError(
            "Application secrets are not initialized"
        )

    currency_cookie = (
        secrets.currency_api_cookie.get_secret_value()
    )

    if not currency_cookie or not currency_cookie.strip():
        raise ValueError(
            "CURRENCY_API_COOKIE is not configured"
        )

    currency_client = CurrencyAPIClient(
        session_cookie=currency_cookie
    )

    cache = APICacheService(
        redis_client=clients.redis
    )

    try:
        logger.info(
            "CURRENCY_CACHE_REFRESH_STARTED"
        )

        # Step 1: Fetch latest currency rates
        currency_data = (
            await currency_client.fetch_rates()
        )

        # Step 2: Prepare cached response
        cache_payload = {
            "refreshed_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "data": currency_data,
        }

        # Step 3: Store in Redis
        await cache.set(
            key=RedisCacheKeys.CURRENCY_RATES,
            data=cache_payload,
            ttl_seconds=(
                settings.currency_cache_ttl_seconds
            ),
        )

        logger.info(
            "CURRENCY_CACHE_REFRESH_SUCCESS"
        )

        return True

    except Exception:
        logger.exception(
            "CURRENCY_CACHE_REFRESH_FAILED"
        )
        return False


async def main():

    clients = None

    try:
        secrets = await load_application_secrets()
        setup_application_insights(
            connection_string=(
                secrets.applicationinsights_connection_string
                .get_secret_value()
            )
        )
        clients = await create_service_clients(secrets)

        marketing_success = await refresh_marketing_cache(
            clients=clients,
            secrets=secrets,
        )
        currency_success = await refresh_currency_cache(
            clients=clients,
            secrets=secrets,
        )

        if not currency_success:
            raise RuntimeError(
                "Currency API cache refresh failed"
            )

        if not marketing_success:
            raise RuntimeError(
                "Marketing API cache refresh failed"
            )

        print("ALL CACHE REFRESHES SUCCESSFUL", flush=True)

    except Exception as exc:

        logger.exception("API_CACHE_REFRESH_JOB_FAILED")

        raise

    finally:

        if clients is not None:
            await close_service_clients(clients)


if __name__ == "__main__":
    asyncio.run(main())
