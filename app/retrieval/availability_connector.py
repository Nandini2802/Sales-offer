
import logging
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings


logger = logging.getLogger(__name__)

# Add other approved hosts only after verifying
# the actual middleware response.
ALLOWED_REPORT_HOSTS = {
    "d39mr55n259x6c.cloudfront.net",
}


class AvailabilityAPIError(Exception):
    pass


class AvailabilityReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_url: str
    file_name: str
    file_type: str
    total_records: int | None = Field(
        default=None,
        ge=0,
    )


class AvailabilityConnector:

    def __init__(self):
        self.settings = get_settings()

    async def download(
        self,
        *,
        project_id: str,
        currency: str,
        file_type: str,
        access_token: str,
        user_id: str,
    ) -> AvailabilityReport:

        if not access_token or not user_id:
            raise AvailabilityAPIError(
                "Authenticated user details are missing."
            )

        headers = {
            "salesforce_access_token": access_token,
            "user_id": user_id,
            "appversion": (
                self.settings.availability_app_version
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "project_id": project_id,
            "currency_code": currency,
            "file_type": file_type,
        }

        try:
            async with AsyncSession(
                impersonate="chrome",
                timeout=self.settings.availability_timeout_seconds,
                allow_redirects=False,
            ) as session:

                response = await session.post(
                    self.settings.availability_api_url,
                    headers=headers,
                    json=payload,
                )

                if response.status_code != 200:
                    logger.error(
                        "AVAILABILITY_API_HTTP_ERROR | "
                        "status_code=%s",
                        response.status_code,
                    )
                    raise AvailabilityAPIError(
                        "Availability middleware returned "
                        f"HTTP {response.status_code}."
                    )

                body = response.json()

        except AvailabilityAPIError:
            raise

        except Exception as exc:
            logger.exception(
                "AVAILABILITY_MIDDLEWARE_REQUEST_FAILED"
            )
            raise AvailabilityAPIError(
                "The availability middleware request failed."
            ) from exc

        metadata = body.get("metaData") or {}

        if (
            str(metadata.get("status")).upper() != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise AvailabilityAPIError(
                "The availability API returned "
                "an unsuccessful result."
            )

        data = body.get("data") or {}

        try:
            report = AvailabilityReport.model_validate(data)
        except Exception as exc:
            raise AvailabilityAPIError(
                "Invalid availability file information."
            ) from exc

        parsed = urlparse(report.file_url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_REPORT_HOSTS
            or parsed.username is not None
            or parsed.password is not None
        ):
            logger.error(
                "AVAILABILITY_FILE_HOST_REJECTED | host=%s",
                parsed.hostname,
            )
            raise AvailabilityAPIError(
                "The report service returned "
                "an unsupported download URL."
            )

        expected_extension = (
            ".pdf" if file_type == "pdf" else ".xlsx"
        )

        if not report.file_name.lower().endswith(
            expected_extension
        ):
            raise AvailabilityAPIError(
                "The returned filename does not match "
                "the requested format."
            )

        if report.file_type.lower() != file_type:
            raise AvailabilityAPIError(
                "The returned file format does not match "
                "the requested format."
            )

        return report
