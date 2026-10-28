import logging
import os

from curl_cffi.requests import AsyncSession
from app.core.config import get_settings


logger = logging.getLogger(__name__)


class UnitComparisonClient:

    def __init__(self):
        settings = get_settings()

        self.url = settings.unit_comparison_api_url
        self.timeout = settings.unit_comparison_timeout_seconds

        if not self.url:
            raise ValueError(
                "UNIT_COMPARISON_API_URL is not configured"
            )

    async def compare_units(
        self,
        token: str,
        user_id: str,
        project_ids: list[str],
        unit_ids: list[str],
    ) -> list[dict]:

        if not token or not user_id:
            raise ValueError("Authentication details missing")

        if (
            len(unit_ids) != 2
            or len(project_ids) != 2
            or not all(unit_ids)
            or not all(project_ids)
            or len(set(unit_ids)) != 2
        ):
            raise ValueError("Exactly two distinct units are required")

        headers = {
            "salesforce_access_token": token,
            "user_id": user_id,
            "Content-Type": "application/json",
        }

        payload = {
            "project_ids": ",".join(project_ids),
            "unit_ids": ",".join(unit_ids),
        }

        async with AsyncSession(timeout=self.timeout) as session:
            response = await session.post(
                self.url,
                headers=headers,
                json=payload,
            )

        response.raise_for_status()

        body = response.json()

        metadata = body.get("metaData") or {}

        if (
            metadata.get("status") != "SUCCESS"
            or metadata.get("statusCode") != 200
        ):
            logger.warning("UNIT_COMPARISON_API_FAILED")
            raise ValueError("Unit comparison API failed")

        data = body.get("data")

        if not isinstance(data, list):
            raise ValueError("Invalid unit comparison response")

        return data