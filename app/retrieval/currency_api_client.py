import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CurrencyAPIClient:

    def __init__(
        self,
        session_cookie: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.settings = get_settings()
        self.session_cookie = session_cookie
        self.http_client = http_client

    async def fetch_rates(self) -> Any:
        """
        Fetch currency rates using the middleware session cookie.
        """

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Cache-Control": "no-cache",
            "User-Agent": "PostmanRuntime/2.11.2",
        }


        logger.info("CURRENCY_API_REQUEST_STARTED")

        async def make_request(client):

            response = await client.get(
                self.settings.currency_api_url,
                headers=headers,
                timeout=60.0,
                follow_redirects=False,
            )

            logger.info(
                "CURRENCY_API_RESPONSE | status=%s",
                response.status_code,
            )

            if response.status_code in (301, 302, 303, 307, 308):
                raise RuntimeError(
                    "Currency API redirected the request. "
                    "The session cookie may be invalid or expired."
                )

            response.raise_for_status()

            data = response.json()

            if data is None or data == {} or data == []:
                raise ValueError(
                    "Currency API returned empty data"
                )

            logger.info(
                "CURRENCY_API_REQUEST_SUCCESS | status=%s",
                response.status_code,
            )

            return data

        try:
            if self.http_client is not None:
                return await make_request(self.http_client)

            async with httpx.AsyncClient() as client:
                return await make_request(client)

        except Exception:
            logger.exception("CURRENCY_API_REQUEST_FAILED")
            raise
