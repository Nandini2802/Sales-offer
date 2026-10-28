import time

from app.observability.logger import audit_event
from app.schemas.handler_result import HandlerResult
from app.schemas.retrieval import InventorySnapshot
from app.handlers.marketing_handler import MarketingHandler
from app.handlers.inventory_handler import InventoryHandler
from app.handlers.payment_plan_handler import PaymentPlanHandler
from app.handlers.availability_handler import AvailabilityHandler
from app.handlers.bank_details_handler import BankDetailsHandler
from app.handlers.sales_offer_handler import SalesOfferHandler
from app.handlers.project_information_handler import ProjectInformationHandler
from app.handlers.walkthrough_handler import WalkthroughHandler
from app.services.walkthrough_access_service import WalkthroughEngine

class IntentDispatcher:

    def __init__(
        self,
        redis_client,
        inventory_snapshot: InventorySnapshot | None = None,
        payment_client=None,
        payment_token: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        access_token: str | None = None,
        message: str = "",
        inventory_token: str | None = None,
        walkthrough_engine: WalkthroughEngine | None = None,
        role: str = "",
        source: str = "",
        employee_type: str = "",
        llm_client=None,
        llm_model: str | None = None,
        selected_payment_plan_names: list[str] | None = None,
    ):

        self.handlers = {
            "marketing": MarketingHandler(redis_client),
        }

        if walkthrough_engine is not None:
            self.handlers["excel_walkthrough"] = WalkthroughHandler(
                engine=walkthrough_engine,
                role=role,
                source=source,
                employee_type=employee_type,
            )

        self.redis_client = redis_client
        self.session_id = session_id
        self.selected_payment_plan_names = selected_payment_plan_names or []

        self.payment_plan_handler = None

        if inventory_snapshot is not None:

            inventory_handler = InventoryHandler(
                inventory_snapshot,
                payment_client=payment_client,
                payment_token=payment_token,
                user_id=user_id,
            )

            self.handlers["inventory"] = inventory_handler

            if (
                payment_client is not None
                and payment_token
                and user_id
            ):
                self.payment_plan_handler = PaymentPlanHandler(
                    snapshot=inventory_snapshot,
                    salesforce_client=payment_client,
                    token=payment_token,
                    user_id=user_id,
                    redis_client=redis_client,
                    session_id=session_id,
                )

            if access_token and user_id:
                self.handlers["bank_details"] = BankDetailsHandler(
                    inventory_snapshot=inventory_snapshot,
                    access_token=access_token,
                    user_id=user_id,
                    message=message,
                )

            if access_token and user_id and session_id:
                self.handlers["sales_offer"] = SalesOfferHandler(
                    inventory_snapshot=inventory_snapshot,
                    redis_client=redis_client,
                    access_token=access_token,
                    user_id=user_id,
                    session_id=str(session_id),
                    message=message,
                    llm_client=llm_client,
                    llm_model=llm_model,
                )

            if inventory_token and access_token:
                self.handlers["project_information"] = (
                    ProjectInformationHandler(
                        inventory_snapshot=inventory_snapshot,
                        inventory_token=inventory_token,
                        access_token=access_token,
                    )
                )

        if (
            inventory_snapshot is not None
            and access_token
            and user_id
        ):
            self.handlers["download_availability"] = (
                AvailabilityHandler(
                    redis_client=redis_client,
                    inventory_snapshot=inventory_snapshot,
                    access_token=access_token,
                    user_id=user_id,
                    walkthrough_engine=walkthrough_engine,
                    role=role,
                    source=source,
                    employee_type=employee_type,
                )
            )

    async def execute(self, intent) -> HandlerResult:

        started_at = time.perf_counter()

        if (
            intent.intent == "inventory"
            and intent.inventory_operation == "payment_plan"
        ):
            handler = self.payment_plan_handler
        else:
            handler = self.handlers.get(intent.intent)

        handler_name = (
            type(handler).__name__
            if handler is not None
            else "NoHandler"
        )

        audit_event(
            "HANDLER_STARTED",
            status="started",
            functionality=intent.intent,
            handler=handler_name,
            operation=getattr(
                intent,
                "inventory_operation",
                None,
            ),
        )

        try:
            if handler is None:
                if intent.intent == "out_of_scope":
                    result = HandlerResult(
                        intent="out_of_scope",
                        messages=[
                            "I can help with Danube Properties "
                            "projects and related services."
                        ],
                    )
                else:
                    result = HandlerResult(
                        intent=intent.intent,
                        messages=[
                            "The requested "
                            f"{intent.intent.replace('_', ' ')} "
                            "service is not available yet."
                        ],
                    )
            else:
                if intent.intent == "sales_offer":
                    result = await handler.handle(
                        intent,
                        selected_payment_plan_names=(
                            self.selected_payment_plan_names
                        ),
                    )
                else:
                    if intent.intent == "sales_offer":
                        result = await handler.handle(
                            intent,
                            selected_payment_plan_names=self.selected_payment_plan_names,
                        )
                    else:
                        result = await handler.handle(intent)

            audit_event(
                "HANDLER_COMPLETED",
                status="success",
                functionality=intent.intent,
                handler=handler_name,
                has_data=result.has_data,
                message_count=len(result.messages),
                latency_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            )

            return result

        except Exception as exc:
            audit_event(
                "HANDLER_FAILED",
                level="ERROR",
                status="failed",
                functionality=intent.intent,
                handler=handler_name,
                error_type=type(exc).__name__,
                latency_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
            )
            raise
