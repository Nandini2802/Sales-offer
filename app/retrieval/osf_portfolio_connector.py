
import logging
import json

from curl_cffi.requests import AsyncSession
from pathlib import Path

from app.core.config import get_settings
from app.core.keyvault import load_application_secrets

logger = logging.getLogger(__name__)


class OSFPortfolioConnector:

    def __init__(self):
        self.settings = get_settings()

    async def fetch_portfolio(self) -> list[dict]:
        url = self.settings.osf_portfolio_api_url

        if not url.startswith("https://"):
            raise ValueError("OSF Portfolio URL is invalid")

        secrets = await load_application_secrets()
        api_key = (
            secrets.osf_portfolio_api_key.get_secret_value()
        )

        if not api_key:
            raise ValueError("OSF Portfolio API key missing")

        headers = {
            "x_api_key": api_key,
            "Accept": "application/json",
        }

        async with AsyncSession(
            impersonate="chrome"
        ) as session:

            response = await session.get(
                url,
                headers=headers,
                timeout=self.settings.osf_portfolio_timeout_seconds,
                allow_redirects=False,
            )


        response.raise_for_status()

        try:
            payload = json.loads(response.text)

            if isinstance(payload, dict):

                projects = payload.get("data", [])

                if isinstance(projects, list):

                    for project in projects:

                        if not isinstance(project, dict):
                            continue

                        title = str(project.get("title") or "")
                        name = str(project.get("name") or "")

                        if not any(
                            keyword in f"{title} {name}".casefold()
                            for keyword in ("greenz", "shahrukhz")
                        ):
                            continue

                        meta = project.get("meta") or {}

        except json.JSONDecodeError:
            raise ValueError(
                "OSF API did not return valid JSON. "
                f"Status: {response.status_code}, "
                f"Content-Type: {response.headers.get('Content-Type')}"
            )

        if not isinstance(payload, dict):
            raise ValueError("Invalid OSF response")

        metadata = payload.get("metaData") or {}

        if (
            metadata.get("status") != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise ValueError("OSF API unsuccessful")

        projects = payload.get("data")

        if not isinstance(projects, list):
            raise ValueError("OSF data is not a list")

        logger.info(
            "OSF_PORTFOLIO_FETCHED | count=%s",
            len(projects),
        )

        return [
            item for item in projects
            if isinstance(item, dict)
        ]
