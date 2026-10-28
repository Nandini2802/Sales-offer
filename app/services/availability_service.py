import json

from app.persistence.redis_store import RedisCacheKeys
from app.services.availability_resolver import resolve_availability_project
from app.retrieval.availability_connector import AvailabilityConnector
from app.utils.availability_debug import availability_debug


DISCLAIMER = (
    "Disclaimer: Exchange rate applied is valid "
    "for today only and subject to change at the "
    "time of unit booking."
)


class AvailabilityValidationError(ValueError):
    pass


def extract_currency_codes(payload) -> set[str]:

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")

    if isinstance(payload, str):
        payload = json.loads(payload)

    # Unwrap known API/cache structures
    for _ in range(5):
        if not isinstance(payload, dict):
            break

        if "data" in payload:
            payload = payload["data"]
        elif "rates" in payload:
            payload = payload["rates"]
        elif "currencies" in payload:
            payload = payload["currencies"]
        elif "currencyRates" in payload:
            payload = payload["currencyRates"]
        else:
            break

    if isinstance(payload, dict):
        return {
            key.upper()
            for key, value in payload.items()
            if isinstance(key, str)
            and len(key) == 3
            and key.isalpha()
            and value is not None
        }

    if isinstance(payload, list):
        codes = set()

        for item in payload:
            if isinstance(item, str):
                code = item
            elif isinstance(item, dict):
                code = (
                    item.get("currency_code")
                    or item.get("currencyCode")
                    or item.get("code")
                )
            else:
                continue

            if (
                isinstance(code, str)
                and len(code) == 3
                and code.isalpha()
            ):
                codes.add(code.upper())

        return codes

    return set()


class AvailabilityService:
    def __init__(self, redis_client, snapshot):
        self.redis = redis_client
        self.snapshot = snapshot
        self.connector = AvailabilityConnector()

    async def generate(
        self,
        *,
        intent,
        access_token: str,
        user_id: str,
    ) -> dict:

        
        # 1. Validate format before calling .strip().
        if not intent.file_format or not str(intent.file_format).strip():
            raise AvailabilityValidationError("Please choose PDF or Excel.")

        aliases = {
            "xlsx": "excel",
            "xls": "excel",
            "spreadsheet": "excel",
        }
        file_type = str(intent.file_format).strip().lower()
        file_type = aliases.get(file_type, file_type)
        if file_type not in {"pdf", "excel"}:
            raise AvailabilityValidationError(
                "Unsupported file format. Please choose PDF or Excel."
            )

        # 2. Validate currency against Redis.
        if not intent.currency or not str(intent.currency).strip():
            raise AvailabilityValidationError("Please select a currency.")
        currency = str(intent.currency).strip().upper()

        cached = await self.redis.get(RedisCacheKeys.CURRENCY_RATES)

        try:
            supported = extract_currency_codes(cached)
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            raise AvailabilityValidationError(
                "Currency information could not be validated."
            ) from exc

        if not supported:
            raise AvailabilityValidationError(
                "Currency information is unavailable."
            )
        if currency not in supported:
            raise AvailabilityValidationError(
                f"{currency} is not a supported currency. "
                "Please select a valid currency."
            )

        

        # 3. Resolve project against the authorized snapshot.
        project = resolve_availability_project(
            intent=intent,
            snapshot=self.snapshot,
        )

        # 4. Call middleware.
        report = await self.connector.download(
            project_id=project.project_id,
            currency=currency,
            file_type=file_type,
            access_token=access_token,
            user_id=user_id,
        )

        # 5. Return verified response.
        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "currency": currency,
            "file_type": file_type,
            "file_name": report.file_name,
            "file_url": report.file_url,
            "total_records": report.total_records,
            "disclaimer": DISCLAIMER,
        }
