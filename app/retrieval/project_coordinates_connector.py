
import logging

from urllib.parse import quote

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class ProjectCoordinatesConnector:

    def __init__(self):
        self.settings = get_settings()

    async def fetch_coordinates(
        self,
        project_id: str,
        access_token: str,
    ):
        base_url = (
            self.settings.project_coordinates_api_url
            .rstrip("/")
        )

        if not base_url.startswith("https://"):
            raise ValueError(
                "PROJECT_COORDINATES_API_URL is invalid"
            )

        if not project_id or not access_token:
            raise ValueError(
                "Project ID and Salesforce token are required"
            )

        url = (
            f"{base_url}/"
            f"{quote(str(project_id), safe='')}"
        )

        headers = {
            "salesforce_access_token": access_token,
            "Accept": "application/json",
        }

        async with AsyncSession(
            impersonate="chrome"
        ) as session:
            response = await session.get(
                url,
                headers=headers,
                timeout=30,
                allow_redirects=False,
            )

        response.raise_for_status()

        payload = response.json()

        metadata = payload.get("metaData") or {}

        if metadata.get("status") != "SUCCESS":
            raise ValueError(
                "Project Coordinates API returned failure"
            )

        data = payload.get("data")

        if not isinstance(data, dict):
            return None

        if str(data.get("Id")) != str(project_id):
            raise ValueError(
                "Coordinates API returned a different project"
            )

        latitude = data.get(
            "LatitudeLongitude__Latitude__s"
        )

        longitude = data.get(
            "LatitudeLongitude__Longitude__s"
        )

        if latitude is None or longitude is None:
            logger.info(
                "PROJECT_COORDINATES_MISSING | project_id=%s",
                project_id,
            )
            return None

        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
        }
