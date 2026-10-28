
import logging

from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class BankDetailsAPIError(Exception):
    pass


class BankAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bankId: str
    bankType: str
    bankName: str
    beneficiaryName: str | None = None
    accountNumber: str | None = None
    ibanNumber: str | None = None
    swiftCode: str | None = None
    branch: str | None = None
    bankLogo: str | None = None


class BankDetailsConnector:

    def __init__(self):
        self.settings = get_settings()

    async def fetch(
        self,
        *,
        project_id: str,
        access_token: str,
        user_id: str,
    ) -> list[BankAccount]:

        if not project_id or not access_token or not user_id:
            raise BankDetailsAPIError(
                "Required project or authentication data missing."
            )

        headers = {
            "salesforce_access_token": access_token,
            "user_id": user_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "projectId": project_id,
        }

        try:
            async with AsyncSession(
                impersonate="chrome",
                timeout=self.settings.bank_details_timeout_seconds,
                allow_redirects=False,
            ) as session:

                response = await session.post(
                    self.settings.bank_details_api_url,
                    headers=headers,
                    json=payload,
                )

                if response.status_code != 200:
                    logger.error(
                        "BANK_API_HTTP_ERROR | status=%s",
                        response.status_code,
                    )
                    raise BankDetailsAPIError(
                        "Bank details service is unavailable."
                    )

                body = response.json()

        except BankDetailsAPIError:
            raise

        except Exception as exc:
            logger.exception(
                "BANK_API_REQUEST_FAILED"
            )
            raise BankDetailsAPIError(
                "Unable to retrieve bank details."
            ) from exc

        if not isinstance(body, dict):
            raise BankDetailsAPIError(
                "Unexpected bank API response."
            )

        metadata = body.get("metaData") or {}

        if not isinstance(metadata, dict):
            raise BankDetailsAPIError(
                "Invalid bank API metadata."
            )

        if (
            str(metadata.get("status")).upper() != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            logger.error(
                "BANK_API_UNSUCCESSFUL | status=%s | code=%s",
                metadata.get("status"),
                metadata.get("statusCode"),
            )
            raise BankDetailsAPIError(
                "Bank details service returned an error."
            )

        data = body.get("data") or {}

        if not isinstance(data, dict):
            raise BankDetailsAPIError(
                "Invalid bank account response."
            )

        raw_accounts = data.get("bankAccounts")

        if not isinstance(raw_accounts, list):
            raise BankDetailsAPIError(
                "Bank account list is missing."
            )

        try:
            accounts = [
                BankAccount.model_validate(account)
                for account in raw_accounts
            ]

        except Exception as exc:
            logger.exception(
                "BANK_ACCOUNT_VALIDATION_FAILED"
            )
            raise BankDetailsAPIError(
                "Invalid bank account information."
            ) from exc

        logger.info(
            "BANK_DETAILS_FETCH_SUCCESS | "
            "project_id=%s | account_count=%s",
            project_id,
            len(accounts),
        )

        return accounts
