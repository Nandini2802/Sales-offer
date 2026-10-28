
import logging
from typing import Any

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def validate_salesforce_response(
    payload: Any,
    *,
    api_name: str,
    require_inventory_status: bool = False,
) -> dict[str, Any]:
    """
    Validate Danube middleware API responses.

    HTTP 200 does not guarantee business success.
    Different APIs have slightly different data envelopes.
    """

    if not isinstance(payload, dict):
        raise AppException(
            "Upstream service returned an invalid response",
            status_code=502,
            error_code="INVENTORY_RESPONSE_ERROR",
        )

    metadata = payload.get("metaData")

    if not isinstance(metadata, dict):
        raise AppException(
            "Upstream service metadata is missing",
            status_code=502,
            error_code="INVENTORY_RESPONSE_ERROR",
        )

    status = str(
        metadata.get("status", "")
    ).strip().upper()

    try:
        status_code = int(metadata.get("statusCode"))
    except (TypeError, ValueError):
        status_code = None

    if status != "SUCCESS" or status_code != 200:
        logger.error(
            "UPSTREAM_BUSINESS_FAILURE | "
            "api=%s | status=%s | code=%s | "
            "developer_message=%s",
            api_name,
            status,
            status_code,
            str(metadata.get("developerMsg", ""))[:300],
        )

        raise AppException(
            "The upstream service reported a failure",
            status_code=502,
            error_code="INVENTORY_UPSTREAM_ERROR",
        )

    data = payload.get("data")

    if not isinstance(data, dict):
        raise AppException(
            "Upstream response data is invalid",
            status_code=502,
            error_code="INVENTORY_RESPONSE_ERROR",
        )

    if require_inventory_status:
        if (
            data.get("StatusCode") != 200
            or data.get("Status") != "Success"
        ):
            raise AppException(
                "Inventory API reported a failure",
                status_code=502,
                error_code="INVENTORY_UPSTREAM_ERROR",
            )

    return data
