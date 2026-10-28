
import logging

from curl_cffi.requests import AsyncSession

from app.core.config import get_settings
from app.retrieval.inventory_normalizer import normalize_project

logger = logging.getLogger(__name__)


class ProjectInformationAPIError(Exception):
    pass


class ProjectInformationConnector:

    def __init__(self):
        self.settings = get_settings()

        
    async def fetch_projects(
        self,
        *,
        inventory_token: str,
        access_token: str,
    ):
        url = self.settings.project_information_api_url

        if not url or not url.startswith("https://"):
            raise ProjectInformationAPIError(
                "Project API URL is not configured."
            )

        if not inventory_token:
            raise ProjectInformationAPIError(
                "Inventory Bearer token is missing."
            )

        if not access_token:
            raise ProjectInformationAPIError(
                "Salesforce access token is missing."
            )

        headers = {
            "Authorization": f"Bearer {inventory_token}",
            "salesforce_access_token": access_token,
            "Accept": "*/*",
        }

        try:
            async with AsyncSession(
                impersonate="chrome"
            ) as session:

                # IMPORTANT: GET, not POST
                response = await session.get(
                    url,
                    headers=headers,
                    allow_redirects=False,
                    timeout=30,
                )

            if response.status_code != 200:
                raise ProjectInformationAPIError(
                    "Project API returned HTTP "
                    f"{response.status_code}."
                )

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "json" not in content_type:
                raise ProjectInformationAPIError(
                    "Project API returned a non-JSON response."
                )

            payload = response.json()

            if not isinstance(payload, dict):
                raise ProjectInformationAPIError(
                    "Invalid project API response."
                )

            metadata = payload.get("metaData") or {}
            data = payload.get("data") or {}

            if (
                metadata.get("status") != "SUCCESS"
                or str(metadata.get("statusCode")) != "200"
            ):
                raise ProjectInformationAPIError(
                    "Project API returned an unsuccessful status."
                )

            if not isinstance(data, dict):
                raise ProjectInformationAPIError(
                    "Invalid project API data."
                )

            projects = data.get("ActiveProjects")

            if not isinstance(projects, list):
                raise ProjectInformationAPIError(
                    "ActiveProjects list is missing."
                )

            # Preserve API ordering for latest projects.
            return [
                normalize_project(project)
                for project in projects
                if isinstance(project, dict)
            ]

        except ProjectInformationAPIError:
            raise

        except Exception as exc:
            logger.exception(
                "PROJECT_INFORMATION_API_FAILED"
            )

            raise ProjectInformationAPIError(
                "Project information is temporarily unavailable."
            ) from exc
