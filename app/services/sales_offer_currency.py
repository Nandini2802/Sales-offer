
import json
from decimal import Decimal, InvalidOperation

from app.persistence.redis_store import RedisCacheKeys


class SalesOfferCurrencyError(Exception):
    pass


async def resolve_sales_offer_currency(
    redis_client,
    currency_code: str,
) -> tuple[str, str]:

    # Default currency
    currency_code = (currency_code or "AED").strip().upper()
    if currency_code == "AED":
        return "AED", "1"

    # Read existing currency cache
    raw = await redis_client.get(
        RedisCacheKeys.CURRENCY_RATES
    )

    if raw is None:
        raise SalesOfferCurrencyError(
            "Currency rates are temporarily unavailable."
        )

    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        payload = (
            json.loads(raw)
            if isinstance(raw, str)
            else raw
        )



        if not isinstance(payload, dict):
            raise ValueError("Invalid currency payload")

        data = payload

        if isinstance(data, dict) and "refreshed_at" in data:
            data = data.get("data", {})

        if isinstance(data, dict) and "data" in data:
            data = data.get("data", {})

        if not isinstance(data, dict):
            raise ValueError("Invalid currency data")

        base = str(data.get("base", "")).upper()

        if base != "AED":
            raise SalesOfferCurrencyError(
                "Unsupported currency base."
            )

        rates = data.get("rates")

        if not isinstance(rates, dict):
            raise ValueError("Currency rates missing")

        if currency_code not in rates:
            raise SalesOfferCurrencyError(
                f"{currency_code} is not available "
                "in the currency rate list."
            )

        rate = Decimal(str(rates[currency_code]))

        if not rate.is_finite() or rate <= 0:
            raise ValueError("Invalid exchange rate")

        return currency_code, str(rate)

    except SalesOfferCurrencyError:
        raise

    except (
        ValueError,
        TypeError,
        InvalidOperation,
    ) as exc:
        raise SalesOfferCurrencyError(
            "Unable to read valid currency rates from Redis."
        ) from exc
