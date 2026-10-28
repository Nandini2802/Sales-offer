import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.scripts.refresh_api_cache import *

logger = logging.getLogger(__name__)


def create_cache_scheduler(clients, secrets):
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Marketing API: every 12 hours
    scheduler.add_job(
        refresh_marketing_cache,
        trigger="cron",
        hour="0,12",
        minute=0,
        args=[clients, secrets],
        id="marketing_cache_refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    logger.info(
        "MARKETING_CACHE_SCHEDULE_CONFIGURED | every_12_hours"
    )

    # Currency Rate API: every 24 hours
    scheduler.add_job(
        refresh_currency_cache,
        trigger="cron",
        hour=0,
        minute=15,
        args=[clients, secrets],
        id="currency_cache_refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    logger.info(
        "API_CACHE_SCHEDULES_CONFIGURED | "
        "marketing=12h | currency=24h"
    )

    return scheduler