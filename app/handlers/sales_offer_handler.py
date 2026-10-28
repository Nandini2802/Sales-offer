
import logging
from urllib.parse import urlparse

from app.schemas.handler_result import HandlerResult
from app.services.template_service import TemplateService

from app.services.sales_offer_resolver import (
    resolve_sales_offer_unit,
    SalesOfferResolutionError,
    resolve_sales_offer_request
)

from app.services.sales_offer_state import SalesOfferState

from app.services.sales_offer_currency import (
    resolve_sales_offer_currency,
    SalesOfferCurrencyError,
)

from app.retrieval.sales_offer_connector import (
    SalesOfferConnector,
    SalesOfferAPIError,
)
from app.schemas.routing import RoutingIntent


logger = logging.getLogger(__name__)


class SalesOfferHandler:

    def __init__(
        self,
        *,
        inventory_snapshot,
        redis_client,
        access_token: str,
        user_id: str,
        session_id: str,
        message: str,
        llm_client=None,
        llm_model: str | None = None,
    ):
        self.snapshot = inventory_snapshot
        self.redis = redis_client
        self.access_token = access_token
        self.user_id = user_id
        self.session_id = session_id
        self.message = message
        self.llm_client = llm_client
        self.llm_model = llm_model

        self.connector = SalesOfferConnector()
        self.state = SalesOfferState(redis_client)
        self.templates = TemplateService()

    def failure(self, message: str) -> HandlerResult:
        return HandlerResult(
            intent="sales_offer",
            messages=[message],
            has_data=False,
        )

    @staticmethod
    def get_document_download_url(document) -> str | None:
        """
        Extract a download URL if the connector
        actually returned one.

        Never construct a URL from a document ID
        without a verified download endpoint.
        """

        if hasattr(document, "model_dump"):
            document_data = document.model_dump()
        elif isinstance(document, dict):
            document_data = document
        else:
            logger.warning(
                "SALES_OFFER_UNKNOWN_DOCUMENT_TYPE | type=%s",
                type(document).__name__,
            )
            return None

        logger.info(
            "SALES_OFFER_DOCUMENT_FIELDS | fields=%s",
            list(document_data.keys()),
        )

        download_url = (
            document_data.get("fileUrl")
            or document_data.get("downloadUrl")
            or document_data.get("file_url")
            or document_data.get("download_url")
        )

        if not isinstance(download_url, str):
            return None

        download_url = download_url.strip()

        parsed = urlparse(download_url)

        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return None

        # IMPORTANT:
        # Restrict parsed.hostname to your approved
        # Salesforce/S3/download domains before
        # deploying this to production.

        return download_url

    async def handle(
        self,
        intent,
        selected_payment_plan_names: list[str] | None = None,
    ) -> HandlerResult:

        try:

            pending = await self.state.load(
                user_id=self.user_id,
                session_id=self.session_id,
            )

            # Sales offer is an explicit state machine:
            # unit -> currency -> payment plans -> generated document.
            selected_numbers = list(getattr(intent, "payment_plan_numbers", None) or [])
            selected_names = [
                name.strip()
                for name in (selected_payment_plan_names or [])
                if isinstance(name, str) and name.strip()
            ]

            # Checkbox names take precedence over LLM-extracted numbers.
            if selected_names:
                selected_numbers = []

            stage = (pending or {}).get("stage")

            visible_units = {
                item.unit_id: item
                for item in self.snapshot.units
                if item.unit_id
            }

            if stage in {"awaiting_currency_selection", "awaiting_payment_plan_selection"}:
                unit_id = pending.get("unit_id")
                unit = visible_units.get(unit_id)
                if unit is None:
                    await self.state.clear(user_id=self.user_id, session_id=self.session_id)
                    return self.failure(
                        "This unit is no longer available in your authorized inventory."
                    )

                if stage == "awaiting_currency_selection":
                    # The router supplies currency on a short currency-only reply.
                    # Never infer AED when the user has not selected a currency.
                    import re
                    raw_currency = (getattr(intent, "currency", None) or "").strip().upper()
                    text = self.message.strip().upper()
                    currency = raw_currency if re.fullmatch(r"[A-Z]{3}", raw_currency) else None
                    if re.fullmatch(r"[A-Z]{3}", text):
                        currency = text
                    if not currency:
                        return self.failure(
                            "Which currency would you like for the sales offer? "
                            "Please enter a three-letter currency code, such as AED, INR or USD."
                        )
                    # Validate against cached supported rates before moving forward.
                    await resolve_sales_offer_currency(self.redis, currency)
                    pending["currency"] = currency
                    pending["stage"] = "awaiting_payment_plan_selection"
                    await self.state.save(
                        user_id=self.user_id,
                        session_id=self.session_id,
                        state=pending,
                    )
                    selected_numbers = []
                else:
                    currency = pending.get("currency")
                    if not currency:
                        return self.failure("Please select a currency before choosing payment plans.")
                    if not selected_numbers:
                        return self.failure(
                            "Please select one or more payment plans from the list."
                        )
            else:
                unit = resolve_sales_offer_unit(intent, self.snapshot)
                unit_id = unit.unit_id
                await self.state.save(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    state={
                        "stage": "awaiting_currency_selection",
                        "unit_id": unit_id,
                        "unit_name": unit.unit_name,
                        "currency": None,
                    },
                )
                return HandlerResult(
                    intent="sales_offer",
                    messages=[
                        f"Unit {unit.unit_name} selected. "
                        "Which currency would you like for the sales offer? "
                        "Please enter a currency code, such as AED, INR or USD."
                    ],
                    has_data=False,
                )

            # ------------------------------------------
            # 3. FETCH FRESH UNIT DETAILS
            # ------------------------------------------

            details = await self.connector.get_unit_details(
                unit_id=unit_id,
                access_token=self.access_token,
            )

            plans = details.payPlanList or []
            offers = details.offerDetails or []

            if selected_names:
                def normalize_plan_name(value: str) -> str:
                    return " ".join(str(value).casefold().split())

                plan_name_to_numbers = {}

                for index, plan in enumerate(plans, start=1):
                    plan_name = getattr(plan, "payPlanName", None)

                    if plan_name:
                        key = normalize_plan_name(plan_name)
                        plan_name_to_numbers.setdefault(key, []).append(index)

                selected_numbers = []
                used_numbers = set()

                for name in selected_names:
                    matches = plan_name_to_numbers.get(
                        normalize_plan_name(name), []
                    )

                    if len(matches) != 1:
                        return self.failure(
                            f"Could not uniquely match payment plan: {name}. "
                            "Please select from the displayed payment plans."
                        )

                    number = matches[0]

                    if number in used_numbers:
                        return self.failure(
                            "The same payment plan was selected more than once."
                        )

                    used_numbers.add(number)
                    selected_numbers.append(number)

            if not plans:

                await self.state.clear(
                    user_id=self.user_id,
                    session_id=self.session_id,
                )

                return self.failure(
                    "No applicable payment plans are "
                    f"available for unit {details.unitName}."
                )

            # ------------------------------------------
            # 4. FIRST TURN: SHOW PAYMENT PLANS
            # ------------------------------------------

            if not selected_numbers:

                await self.state.save(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    state={
                        "stage": "awaiting_payment_plan_selection",
                        "unit_id": unit_id,
                        "unit_name": details.unitName,
                        "currency": currency,
                        "plan_ids": [
                            plan.payPlanId
                            for plan in plans
                        ],
                    },
                )

                html = self.templates.render(
                    "sales_offer_plans.html.j2",
                    unit_name=details.unitName,
                    plans=[
                        plan.model_dump()
                        for plan in plans
                    ],
                )

                return HandlerResult(
                    intent="sales_offer",
                    html_blocks=[
                        {
                            "card_type": "sales_offer_plans",
                            "html": html,
                        }
                    ],
                    messages=[
                        f"The sales offer will be generated in {currency}. "
                        "Your sales offer is almost ready. "
                        "Please select your preferred payment plans "
                        "or type their names or option numbers."
                    ],
                    has_data=False,
                )

            # ------------------------------------------
            # 5. VALIDATE PENDING SELECTION
            # ------------------------------------------

            if not pending:

                return self.failure(
                    "Your payment-plan selection "
                    "has expired. Please request "
                    "the sales offer again."
                )

            original_ids = pending.get(
                "plan_ids", []
            )

            if (
                not selected_numbers
                or len(set(selected_numbers))
                != len(selected_numbers)
                or any(
                    number < 1
                    or number > len(original_ids)
                    for number in selected_numbers
                )
            ):

                return self.failure(
                    "Please select valid payment-plan "
                    "numbers from the displayed list."
                )

            selected_ids = [
                original_ids[number - 1]
                for number in selected_numbers
            ]

            # ------------------------------------------
            # 6. REVALIDATE PAYMENT PLANS
            # ------------------------------------------

            current_ids = {
                plan.payPlanId
                for plan in plans
            }

            if not all(
                plan_id in current_ids
                for plan_id in selected_ids
            ):

                await self.state.clear(
                    user_id=self.user_id,
                    session_id=self.session_id,
                )

                return self.failure(
                    "The payment plans have changed. "
                    "Please start a new sales offer request."
                )

            # ------------------------------------------
            # 7. RESOLVE SALES OFFER ID
            # ------------------------------------------

            # Empty offerId is supported for generating
            # a sales offer without a separate offer.

            offer_id = ""

            if offers:

                return self.failure(
                    "This unit has additional sales offers. "
                    "Please select an applicable offer "
                    "before generation."
                )

            # ------------------------------------------
            # 8. RESOLVE CURRENCY FROM REDIS
            # ------------------------------------------

            currency_code, exchange_rate = (
                await resolve_sales_offer_currency(
                    self.redis,
                    currency,
                )
            )

            logger.info(
                "SALES_OFFER_CURRENCY | "
                "currency=%s | exchange_rate=%s",
                currency_code,
                exchange_rate,
            )

            # ------------------------------------------
            # 9. GENERATE SALES OFFER
            # ------------------------------------------

            generated = await self.connector.generate(
                unit_id=unit_id,
                unit_name=details.unitName,
                offer_id=offer_id,
                payment_plan_ids=selected_ids,
                currency_code=currency_code,
                exchange_rate=exchange_rate,
                access_token=self.access_token,
            )

            if not generated:

                return self.failure(
                    "The Sales Offer API did not "
                    "return any generated documents."
                )

            logger.info(
                "SALES_OFFER_GENERATED | "
                "unit=%s | document_count=%s",
                details.unitName,
                len(generated),
            )


            # ------------------------------------------
            # 10. BUILD SALES OFFER PDF FILE CARDS
            # ------------------------------------------

            html_blocks = []
            files = []
            document_names = []

            for document in generated:

                file_name = document.salesOfferName
                document_names.append(file_name)

                download_url = (
                    self.get_document_download_url(
                        document
                    )
                )

                if not download_url:

                    logger.warning(
                        "SALES_OFFER_DOWNLOAD_URL_MISSING | "
                        "file=%s",
                        file_name,
                    )


                html = self.templates.render(
                    "sales_offer_file.html.j2",
                    file_name=file_name,
                    download_url=download_url,
                )

                html_blocks.append(
                    {
                        "card_type": "sales_offer_file",
                        "html": html,
                    }
                )

                files.append(
                    {
                        "name": file_name,
                        "type": "sales_offer",
                        "format": "pdf",
                        "download_url": download_url,
                    }
                )

            # ------------------------------------------
            # 11. CLEAR COMPLETED PENDING STATE
            # ------------------------------------------

            await self.state.clear(
                user_id=self.user_id,
                session_id=self.session_id,
            )

            # ------------------------------------------
            # 12. RETURN SUCCESSFUL HANDLER RESULT
            # ------------------------------------------

            return HandlerResult(
                intent="sales_offer",

                # The generation LLM produces the
                # confirmation text. Do not duplicate it.
                messages=[
                    f"The sales offer for unit {details.unitName} has been generated "
                    f"in {currency_code}. "
                    + "Generated document(s): " + ", ".join(document_names) + "."
                ],

                # Rendered PDF download cards
                html_blocks=html_blocks,

                # File metadata
                files=files,

                generation_context={
                    "service": "sales_offer",
                    "generated": True,
                    "project_name": getattr(
                        unit,
                        "project_name",
                        None,
                    ),
                    "unit_name": details.unitName,
                    "currency": currency_code,
                    "exchange_rate": exchange_rate,
                    "exchange_rate_direction": "AED_TO_TARGET",
                    "document_count": len(generated),
                    "document_names": document_names,
                },

                has_data=True,
            )

        # ----------------------------------------------
        # 13. ERROR HANDLING
        # ----------------------------------------------

        except SalesOfferResolutionError as exc:

            return self.failure(str(exc))

        except SalesOfferCurrencyError as exc:

            return self.failure(str(exc))

        except SalesOfferAPIError:

            logger.exception(
                "SALES_OFFER_API_FAILED"
            )

            return self.failure(
                "The sales offer could not be "
                "generated right now. "
                "Please try again."
            )

        except Exception:

            logger.exception(
                "SALES_OFFER_UNEXPECTED_ERROR | "
                "session_id=%s",
                self.session_id,
            )

            raise
