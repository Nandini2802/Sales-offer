
import logging

from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SalesOfferAPIError(Exception):
    pass


class PaymentPlan(BaseModel):
    payPlanId: str
    payPlanName: str


class OfferDetail(BaseModel):
    model_config = ConfigDict(extra="allow")


class UnitOfferDetails(BaseModel):
    unitId: str
    unitName: str
    payPlanList: list[PaymentPlan] = Field(
        default_factory=list
    )
    offerDetails: list[dict] = Field(
        default_factory=list
    )


class GeneratedSalesOffer(BaseModel):
    unitId: str
    salesOfferName: str
    salesOfferDocId: str


class SalesOfferConnector:

    def __init__(self):
        self.settings = get_settings()

    async def _post(
        self,
        *,
        url: str,
        payload,
        access_token: str,
    ):
        if not access_token:
            raise SalesOfferAPIError(
                "Authenticated Salesforce token is missing."
            )

        headers = {
            "salesforce_access_token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with AsyncSession(
                impersonate="chrome",
                timeout=self.settings.sales_offer_timeout_seconds,
                allow_redirects=False,
            ) as session:
                response = await session.post(
                    url,
                    headers=headers,
                    json=payload,
                )

            if response.status_code != 200:
                logger.error(
                    "SALES_OFFER_HTTP_ERROR | status=%s",
                    response.status_code,
                )
                raise SalesOfferAPIError(
                    "Sales offer middleware request failed."
                )

            body = response.json()

        except SalesOfferAPIError:
            raise
        except Exception as exc:
            logger.exception("SALES_OFFER_REQUEST_FAILED")
            raise SalesOfferAPIError(
                "Unable to contact sales offer service."
            ) from exc

        if not isinstance(body, dict):
            raise SalesOfferAPIError(
                "Unexpected middleware response."
            )

        metadata = body.get("metaData") or {}

        if (
            str(metadata.get("status")).upper() != "SUCCESS"
            or str(metadata.get("statusCode")) != "200"
        ):
            raise SalesOfferAPIError(
                "Sales offer service returned an error."
            )

        return body.get("data")

    async def get_unit_details(
        self,
        *,
        unit_id: str,
        access_token: str,
    ) -> UnitOfferDetails:

        data = await self._post(
            url=self.settings.sales_offer_unit_details_url,
            payload={"unitId": unit_id},
            access_token=access_token,
        )

        try:
            result = UnitOfferDetails.model_validate(data)
        except Exception as exc:
            raise SalesOfferAPIError(
                "Invalid unit details response."
            ) from exc

        if result.unitId != unit_id:
            raise SalesOfferAPIError(
                "Unit details response ID mismatch."
            )

        return result

    async def generate(
        self,
        *,
        unit_id: str,
        unit_name: str,
        offer_id: str,
        payment_plan_ids: list[str],
        currency_code: str,
        exchange_rate: str,
        access_token: str,
    ) -> list[GeneratedSalesOffer]:

        payload = [{
            "unitId": unit_id,
            "unitName": unit_name,
            "offerId": offer_id,
            "paymentPlanIds": payment_plan_ids,
            "currencyCode": currency_code,
            "exchangeRate": exchange_rate,
        }]

        data = await self._post(
            url=self.settings.sales_offer_generate_url,
            payload=payload,
            access_token=access_token,
        )

        if not isinstance(data, list) or not data:
            raise SalesOfferAPIError(
                "No generated sales offer was returned."
            )

        try:
            offers = [
                GeneratedSalesOffer.model_validate(item)
                for item in data
            ]
        except Exception as exc:
            raise SalesOfferAPIError(
                "Invalid generated offer response."
            ) from exc

        if any(offer.unitId != unit_id for offer in offers):
            raise SalesOfferAPIError(
                "Generated offer unit ID mismatch."
            )

        return offers
