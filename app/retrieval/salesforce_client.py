import asyncio
import logging
import re
import time

from typing import Any
from curl_cffi.requests import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.keyvault import AppSecrets
from app.retrieval.salesforce_response_validator import validate_salesforce_response
from app.observability.logger import audit_event

logger = logging.getLogger(__name__)


class SalesforceClient:
    """Danube Inventory APIs. Use only authorized credentials and WAF access."""

    def __init__(
        self,
        http_client: AsyncSession | None = None,
        secrets: AppSecrets | None = None,
    ):
        self.settings = get_settings()
        self.http_client = http_client
        self.secrets = secrets

    async def _request(
        self,
        url: str,
        token: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if not url or not url.startswith("https://"):
            raise AppException(
                "Inventory API URL is not configured securely",
                status_code=500,
                error_code="INVENTORY_CONFIGURATION_ERROR",
            )
        if not token or not token.strip():
            raise AppException(
                "Authentication token is required",
                status_code=401,
                error_code="AUTHENTICATION_ERROR",
            )

        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Accept": "*/*",
        }
        if user_id is not None:
            if not user_id.strip():
                raise AppException(
                    "Authenticated user ID is required",
                    status_code=401,
                    error_code="AUTHENTICATION_ERROR",
                )
            headers["user_id"] = user_id.strip()

        # Test-only cookie: never hardcode it or depend on it in production.
        cookie = (
            self.secrets.inventory_test_cookie
            .get_secret_value()
            .strip()
        )
        if cookie:
            headers["Cookie"] = f"sess_map={cookie}"

        max_attempts = max(1, self.settings.inventory_max_retries)

        async def execute(session: AsyncSession) -> dict[str, Any]:
            for attempt in range(max_attempts):
                try:
                    request_started = time.perf_counter()
                    response = await session.get(
                        url,
                        headers=headers,
                        timeout=self.settings.inventory_timeout_seconds,
                    )

                    audit_event(
                        "INVENTORY_API_HTTP_RESPONSE",
                        status=(
                            "success"
                            if response.status_code < 400
                            else "failed"
                        ),
                        http_status=response.status_code,
                        latency_ms=round(
                            (time.perf_counter() - request_started) * 1000,
                            2,
                        ),
                        attempt=attempt + 1,
                    )

                    if response.status_code in (401, 403):
                        raise AppException(
                            "Inventory authorization failed",
                            status_code=response.status_code,
                            error_code="INVENTORY_ACCESS_ERROR",
                        )

                    if response.status_code in (502, 503, 504) and attempt < max_attempts - 1:
                        await asyncio.sleep(min(2 ** attempt, 4))
                        continue

                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")

                        logger.warning(
                            "INVENTORY_RATE_LIMITED | endpoint=%s | status=%s | retry_after=%s",
                            url.split("?")[0],
                            response.status_code,
                            retry_after,
                        )

                        raise AppException(
                            "Inventory service rate limit exceeded",
                            status_code=503,
                            error_code="INVENTORY_RATE_LIMITED",
                        )

                    if response.status_code >= 400:
                        logger.warning(
                            "INVENTORY_HTTP_FAILED | status=%s | endpoint=%s | content_type=%s",
                            response.status_code,
                            url.split("?")[0],
                            response.headers.get("content-type"),
                        )
                        logger.error(
                            "SALESFORCE_API_FAILED | "
                            "status=%s | "
                            "reason=%s",
                            response.status_code,
                            response.reason_phrase,
                        )
                                                
                        raise AppException(
                            "Inventory service request failed",
                            status_code=502,
                            error_code="INVENTORY_UPSTREAM_ERROR",
                        )

                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise AppException(
                            "Inventory API returned invalid JSON",
                            status_code=502,
                            error_code="INVENTORY_RESPONSE_ERROR",
                        ) from exc

                    metadata = payload.get("metaData") or {}
                    data = payload.get("data") or {}

                    validate_salesforce_response(
                        payload,
                        api_name="Inventory API",
                        require_inventory_status=True,
                    )

                    return payload

                except AppException:
                    raise
                except Exception as exc:
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(min(2 ** attempt, 4))
                        continue
                    logger.warning(
                        "INVENTORY_TRANSPORT_FAILED | error_type=%s",
                        type(exc).__name__,
                    )
                    raise AppException(
                        "Inventory service is temporarily unavailable",
                        status_code=503,
                        error_code="INVENTORY_UPSTREAM_ERROR",
                    ) from exc

            raise AppException(
                "Inventory request failed after retries",
                status_code=503,
                error_code="INVENTORY_UPSTREAM_ERROR",
            )

        if self.http_client is not None:
            return await execute(self.http_client)

        async with AsyncSession(impersonate="chrome") as session:
            return await execute(session)

    async def get_active_projects(self, token: str) -> list[dict]:
        payload = await self._request(
            url=self.settings.inventory_project_api_url,
            token=token,
        )
        projects = payload["data"].get("ActiveProjects")
        if not isinstance(projects, list) or not all(isinstance(p, dict) for p in projects):
            raise AppException(
                "ActiveProjects is missing or invalid",
                status_code=502,
                error_code="INVENTORY_RESPONSE_ERROR",
            )
        audit_event(
            "INVENTORY_API_DATA_VALIDATED",
            api="active_projects",
            status="success",
            record_count=len(projects),
        )
        return projects

    async def get_visible_units(self, token: str, user_id: str) -> list[dict]:
        payload = await self._request(
            url=self.settings.inventory_units_api_url,
            token=token,
            user_id=user_id,
        )
        units = payload["data"].get("Units")
        if not isinstance(units, list) or not all(isinstance(u, dict) for u in units):
            raise AppException(
                "Units is missing or invalid",
                status_code=502,
                error_code="INVENTORY_RESPONSE_ERROR",
            )
        audit_event(
            "INVENTORY_API_DATA_VALIDATED",
            api="visible_units",
            status="success",
            record_count=len(units),
        )
        return units

    async def get_payment_plans(
        self,
        token: str,
        user_id: str,
        unit_id: str,
    ) -> list[dict]:
        """
        Fetch payment plans for an authorized Salesforce unit.
        """

        if not token or not token.strip():
            raise AppException(
                "Payment plan authentication is required",
                status_code=401,
                error_code="AUTHENTICATION_ERROR",
            )

        if not user_id or not user_id.strip():
            raise AppException(
                "Authenticated user ID is required",
                status_code=401,
                error_code="AUTHENTICATION_ERROR",
            )

        if not re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?", unit_id):
            raise AppException(
                "Invalid Salesforce unit ID",
                status_code=400,
                error_code="INVALID_UNIT_ID",
            )

        base_url = self.settings.payment_plan_api_url.rstrip("/")

        if not base_url.startswith("https://"):
            raise AppException(
                "Payment Plan API URL is not configured securely",
                status_code=500,
                error_code="INVENTORY_CONFIGURATION_ERROR",
            )

        url = f"{base_url}/{unit_id}"

        headers = {
            "salesforce_access_token": token.strip(),
            "user_id": user_id.strip(),
            "Accept": "application/json",
        }

        async def execute(session):
            try:
                response = await session.get(
                    url,
                    headers=headers,
                    timeout=self.settings.payment_plan_timeout_seconds,
                )
            except Exception as exc:
                logger.warning(
                    "PAYMENT_PLAN_TRANSPORT_FAILED | error=%s",
                    type(exc).__name__,
                )
                raise AppException(
                    "Payment Plan service is unavailable",
                    status_code=503,
                    error_code="INVENTORY_UPSTREAM_ERROR",
                ) from exc

            if response.status_code in (401, 403):
                raise AppException(
                    "Payment Plan authorization failed",
                    status_code=response.status_code,
                    error_code="INVENTORY_ACCESS_ERROR",
                )

            if response.status_code == 429:
                raise AppException(
                    "Payment Plan service rate limit exceeded",
                    status_code=503,
                    error_code="INVENTORY_RATE_LIMITED",
                )

            if response.status_code >= 400:
                raise AppException(
                    "Payment Plan upstream request failed",
                    status_code=502,
                    error_code="INVENTORY_UPSTREAM_ERROR",
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise AppException(
                    "Payment Plan API returned invalid JSON",
                    status_code=502,
                    error_code="INVENTORY_RESPONSE_ERROR",
                ) from exc

            metadata = (
                payload.get("metaData", {})
                if isinstance(payload, dict)
                else {}
            )

            data = validate_salesforce_response(
                payload,
                api_name="Payment Plan API",
            )

            if data.get("status") != "Success":
                raise AppException(
                    "Payment Plan API reported a failure",
                    status_code=502,
                    error_code="INVENTORY_UPSTREAM_ERROR",
                )

            plans = data.get("paymentPlans")

            if (
                not isinstance(plans, list)
                or not all(isinstance(p, dict) for p in plans)
            ):
                raise AppException(
                    "Invalid paymentPlans response",
                    status_code=502,
                    error_code="INVENTORY_RESPONSE_ERROR",
                )

            return plans

        if self.http_client is not None:
            return await execute(self.http_client)

        async with AsyncSession(impersonate="chrome") as session:
            return await execute(session)
