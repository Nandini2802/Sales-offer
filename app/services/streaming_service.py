import time
import asyncio
import logging
import uuid
import json
import re
import os

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.project_name_service import normalize_project_name
from app.services.project_resolution_service import (
    resolve_project,
    match_project_reference,
)
from app.core.config import get_settings
from app.core.clients import ServiceClients
from app.schemas.chat import ChatResponse
from app.schemas.streaming import HTMLBlockEvent
from app.schemas.errors import ErrorResponse, ErrorDetail
from app.services.router_service import RouterService
from app.services.session_service import SessionService
from app.services.generation_service import GenerationService, build_marketing_generation_context
from app.utils.sse import format_sse
from app.services.project_catalog_service import ProjectCatalogService
from app.handlers.dispatcher import IntentDispatcher
from app.persistence.redis_store import RedisCacheKeys
from app.retrieval.salesforce_client import SalesforceClient
from app.retrieval.inventory_connector import InventoryConnector
from app.services.inventory_catalog_service import InventoryCatalogService
from app.services.inventory_token_provider import get_inventory_token_service
from app.retrieval.project_name import resolve_project_name
from app.services.inventory_conversation_service import *
from app.core.keyvault import load_application_secrets
from app.services.payment_plan_context_service import (
    load_pending_payment_selection,
    match_selected_plan,
    clear_pending_payment_selection,
)
from app.services.availability_resolver import (
    resolve_availability_project,
    AvailabilityResolutionError,
)
from app.services.sales_offer_state import SalesOfferState
from app.services.walkthrough_access_service import WalkthroughEngine
from app.services.download_availability_state import DownloadAvailabilityState
from app.services.download_availability_access_service import DownloadAvailabilityAccessService
from app.observability.logger import audit_event, log_context
from app.services.payment_plan_selection_service import interpret_payment_selection

from app.utils.bank_debug import bank_debug



logger = logging.getLogger(__name__)
settings = get_settings()
real_llm_streaming = False
streamed_answer = ""

def is_real_streaming_enabled() -> bool:
    return (
        os.getenv(
            "ENABLE_REAL_LLM_STREAMING", "false"
        ).strip().lower() == "true"
    )

GREETING_RESPONSE = """Hi, I can help you with:

- Marketing material for any project.
- Guidance on finding features in the App and how to use videos.
- Finding relevant inventory for your customers.
- Project information, including 3D links, bank details, map locations, FAQs, project details, and construction updates.
- Unit details, including layout plans and payment plans.
- Comparing units and projects.
- Downloading unit availability for a project and sales offers for a unit."""



async def persist_completed_chat(
    clients,
    session_id,
    user_id,
    user_message,
    assistant_message,
    intents,
    latency_ms,
    response_payload: dict | None = None,
):

    save_started = time.perf_counter()

    audit_event(
        "POSTGRES_CHAT_SAVE_STARTED",
        status="started",
        session_id=str(session_id),
        intents=intents,
    )

    try:
        session_factory = async_sessionmaker(
            bind=clients.postgres,
            expire_on_commit=False,
            autoflush=False,
        )

        async with session_factory() as db:

            service = SessionService(db)

            saved_records = (
                await service.save_completed_exchange(
                    session_id=session_id,
                    user_id=user_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    intents=intents,
                    latency_ms=latency_ms,
                    response_payload=response_payload,
                )
            )

        audit_event(
            "POSTGRES_CHAT_SAVE_SUCCESS",
            status="success",
            session_id=str(session_id),
            latency_ms=round(
                (time.perf_counter() - save_started) * 1000,
                2,
            ),
        )

        return saved_records

    except Exception as exc:

        audit_event(
            "POSTGRES_CHAT_SAVE_FAILED",
            level="ERROR",
            status="failed",
            session_id=str(session_id),
            error_type=type(exc).__name__,
            latency_ms=round(
                (time.perf_counter() - save_started) * 1000,
                2,
            ),
        )

        raise

async def load_chat_history(
    clients,
    session_id,
    user_id,
    limit=10,
):
    """
    Retrieve recent conversation messages
    from PostgreSQL.
    """

    session_factory = async_sessionmaker(
        bind=clients.postgres,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as db:

        service = SessionService(db)

        history = await service.get_recent_context(
            session_id=session_id,
            user_id=user_id,
            message_limit=limit,
        )

        return history

async def load_previous_inventory_context(
    clients,
    session_id,
    user_id,
):
    session_factory = async_sessionmaker(
        bind=clients.postgres,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as db:
        service = SessionService(db)

        return await service.get_latest_inventory_context(
            session_id=session_id,
            user_id=user_id,
        )

async def _stream_chat_response_impl(
    message: str,
    session_id: uuid.UUID,
    correlation_id: str,
    user_id: str,
    role: str,
    source: str,
    employee_type: str,
    clients: ServiceClients,
    access_token: str,
    walkthrough_engine: WalkthroughEngine,
    selected_payment_plan_names: list[str] | None = None,
):

    started_at = time.perf_counter()

    status = "failed"

    logger.info(
        "Chat stream started | correlation_id=%s | session_id=%s",
        correlation_id,
        session_id,
    )

    try:
        # 1. SESSION EVENT

        yield format_sse(
            "session",
            {
                "session_id": str(session_id),
                "correlation_id": correlation_id,
            },
        )

        # 2. CLASSIFY USER QUERY

        settings = get_settings()

        router_service = RouterService(
            client=clients.foundry_openai,
            model=settings.foundry_openai_model,
        )

        history = await load_chat_history(
            clients=clients,
            session_id=session_id,
            user_id=user_id,
            limit=10,
        )

        pending_payment_selection = await load_pending_payment_selection(
            redis_client=clients.redis,
            user_id=user_id,
            session_id=str(session_id),
        )

        selected_payment_plan = None
        payment_selection_decision = None


        if pending_payment_selection:
            payment_selection_decision = (
                await interpret_payment_selection(
                    message=message,
                    plans=pending_payment_selection["plans"],
                    llm_client=clients.foundry_openai,
                    model=settings.foundry_openai_model,
                )
            )

            if payment_selection_decision.status == "selected":
                selected_payment_plan = (
                    payment_selection_decision.plan
                )

            logger.info(
                "PAYMENT_PLAN_FOLLOWUP | session_id=%s | "
                "status=%s",
                session_id,
                payment_selection_decision.status,
            )




        # Download Availability pending selection (scoped to authenticated user/session).
        availability_state = DownloadAvailabilityState(clients.redis)
        pending_availability = await availability_state.load(
            user_id=user_id, session_id=str(session_id),
        )
        availability_followup = False
        routing_message = message
        if pending_availability:
            normalized_reply = message.strip().lower()
            if normalized_reply in {"cancel", "never mind", "nevermind", "stop"}:
                await availability_state.clear(
                    user_id=user_id, session_id=str(session_id),
                )
                pending_availability = None
            else:
                # Preserve the ordinary router for new requests. Only clearly
                # parameter-only answers are treated as continuations.
                tokens = message.strip().split()
                is_currency_reply = (
                    len(tokens) == 1 and len(tokens[0]) == 3
                    and tokens[0].isalpha()
                )
                is_format_reply = normalized_reply in {
                    "pdf", "excel", "xls", "xlsx", "spreadsheet",
                    "pdf instead", "excel instead",
                }
                if is_currency_reply or is_format_reply:
                    availability_followup = True
                    routing_message = (
                        "Continue my pending download_availability request "
                        f"for {pending_availability.get('project_name') or pending_availability.get('project_id') or 'the project'}. "
                        f"My answer to your clarification is: {message}"
                    )

        # Load official project names from Redis
        project_catalog_service = ProjectCatalogService(
            redis_client=clients.redis,
        )

        secrets = await load_application_secrets()

        inventory_client = SalesforceClient(
            secrets=secrets
        )
        inventory_connector = InventoryConnector(
            salesforce_client=inventory_client
        )

        inventory_token_service = get_inventory_token_service(secrets=secrets)

        inventory_token = await inventory_token_service.get_token()

        inventory_snapshot = (
            await inventory_connector.fetch_inventory(
                token=inventory_token,
                user_id=user_id,
            )
        )

        # PAYMENT PLAN FOLLOW-UP: exact selection bypasses LLM routing.
        # Reuse the existing handler, HTML renderer, persistence, and SSE format.
        if selected_payment_plan is not None:
            from types import SimpleNamespace
            from app.handlers.payment_plan_handler import PaymentPlanHandler

            payment_handler = PaymentPlanHandler(
                snapshot=inventory_snapshot,
                salesforce_client=inventory_client,
                token=access_token,
                user_id=user_id,
                redis_client=clients.redis,
                session_id=str(session_id),
            )

            selected_intent = SimpleNamespace(
                unit_number=pending_payment_selection["unit_id"],
                project_name=None,
                project_number=None,
            )
            selection_result = await payment_handler.handle(
                selected_intent,
                selected_plan_id=selected_payment_plan["id"],
            )

            selection_html = [
                HTMLBlockEvent(
                    card_type=block["card_type"],
                    html=block["html"],
                ).model_dump(mode="json")
                for block in selection_result.html_blocks
            ]
            selection_succeeded = (
                selection_result.has_data and bool(selection_html)
            )
            selection_text = (
                f"Here is the selected payment plan for "
                f"{pending_payment_selection['unit_name']}: "
                f"{selected_payment_plan['name']}."
                if selection_succeeded
                else " ".join(selection_result.messages)
                or "The selected payment plan could not be displayed."
            )
            selection_payload = {
                "version": 1,
                "html_blocks": selection_html,
                "files": selection_result.files,
                "followups": [],
                "inventory_context": None,
            }
            selection_response = ChatResponse(
                response=selection_text,
                session_id=session_id,
                correlation_id=correlation_id,
                followups=[],
                data={
                    "files": selection_result.files,
                    "classification": {
                        "intents": [{
                            "intent": "inventory",
                            "inventory_operation": "payment_plan",
                        }],
                        "payment_plan_followup": True,
                    },
                },
            )
            await persist_completed_chat(
                clients=clients,
                session_id=session_id,
                user_id=user_id,
                user_message=message,
                assistant_message=selection_text,
                intents=["inventory"],
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                response_payload=selection_payload,
            )

            if selection_succeeded:
                await clear_pending_payment_selection(
                    redis_client=clients.redis,
                    user_id=user_id,
                    session_id=str(session_id),
                )

            yield format_sse("token", {"text": selection_text})
            for block in selection_html:
                yield format_sse("html_block", block)
            yield format_sse("followups", {"chips": []})
            yield format_sse(
                "final",
                selection_response.model_dump(mode="json"),
            )
            status = "completed"
            yield format_sse("done", {"status": status})
            return

        
        if (
            payment_selection_decision is not None
            and payment_selection_decision.status == "clarify"
        ):
            clarification_text = (
                payment_selection_decision.message
                or "Please select one payment plan."
            )

            clarification_payload = {
                "version": 1,
                "html_blocks": [],
                "files": [],
                "followups": [],
                "inventory_context": None,
            }

            clarification_response = ChatResponse(
                response=clarification_text,
                session_id=session_id,
                correlation_id=correlation_id,
                followups=[],
                data={
                    "files": [],
                    "classification": {
                        "intents": [{
                            "intent": "inventory",
                            "inventory_operation": "payment_plan",
                        }],
                        "payment_plan_followup": True,
                        "requires_clarification": True,
                    },
                },
            )

            await persist_completed_chat(
                clients=clients,
                session_id=session_id,
                user_id=user_id,
                user_message=message,
                assistant_message=clarification_text,
                intents=["inventory"],
                latency_ms=int(
                    (time.perf_counter() - started_at) * 1000
                ),
                response_payload=clarification_payload,
            )

            yield format_sse(
                "token",
                {"text": clarification_text},
            )
            yield format_sse(
                "followups",
                {"chips": []},
            )
            yield format_sse(
                "final",
                clarification_response.model_dump(mode="json"),
            )
            yield format_sse(
                "done",
                {"status": "completed"},
            )
            return

        if (
            payment_selection_decision is not None
            and payment_selection_decision.status == "new_request"
        ):
            await clear_pending_payment_selection(
                redis_client=clients.redis,
                user_id=user_id,
                session_id=str(session_id),
            )



        previous_inventory_context = await load_previous_inventory_context(
            clients=clients,
            session_id=session_id,
            user_id=user_id,
        )

        previous_authorized_units = resolve_authorized_units(
            previous_inventory_context,
            inventory_snapshot,
        )

        previous_inventory_context = (
            {
                "project_name": previous_inventory_context.get("project_name"),
                "operation": previous_inventory_context.get("operation"),
                "unit_numbers": [
                    unit.unit_name
                    for unit in previous_authorized_units
                    if unit.unit_name
                ],
                "total_matches": len(previous_authorized_units),
            }
            if previous_inventory_context
            else None
        )


        active_project_names = list(
            dict.fromkeys(
                project.project_name
                for project in inventory_snapshot.projects
                if project.project_name
            )
        )


        inventory_catalogs = InventoryCatalogService.build(
            inventory_snapshot
        )

        available_projects = (
            await project_catalog_service.get_project_names()
        )

        if not available_projects:
            raise RuntimeError(
                "Project catalog is unavailable or empty"
            )

        active_project_names = active_project_names or []

        walkthrough_features = [
            guide.name
            for guide in walkthrough_engine.guides.values()
        ]
        
        # LLM 1 receives the official project catalog
        routing_result = await router_service.classify(
            message=routing_message,
            history=history,
            available_projects=available_projects,
            inventory_active_projects=inventory_catalogs.active_projects,
            inventory_unit_projects=inventory_catalogs.unit_projects,
            active_project_names=active_project_names,
            previous_inventory_context=previous_inventory_context,
            walkthrough_features=walkthrough_features,
        )

        audit_event(
            "LLM1_COMPLETED",
            correlation_id=correlation_id,
            session_id=str(session_id),
            llm1_response=(
                routing_result.model_dump_json()
                if hasattr(routing_result, "model_dump_json")
                else str(routing_result)
            ),
        )

        logger.info(
            "WALKTHROUGH_ROUTER_RESULT | features=%s",
            [
                intent.feature_name
                for intent in routing_result.intents
                if intent.intent == "excel_walkthrough"
            ],
        )


        # Merge pending parameters after LLM 1; do not let LLM defaults
        # overwrite a previously explicit user selection.
        availability_intents = [
            item for item in routing_result.intents
            if item.intent == "download_availability"
        ]
        if pending_availability and availability_followup and not availability_intents:
            # Do not execute an unrelated intent on an ambiguous continuation.
            logger.warning("AVAILABILITY_FOLLOWUP_NOT_CLASSIFIED | session_id=%s", session_id)
        if pending_availability and availability_intents and availability_followup:
            for item in availability_intents:
                if not any((item.project_id, item.project_name, item.project_number,
                            item.unit_id, item.unit_name, item.unit_number)):
                    item.project_id = pending_availability.get("project_id")
                    item.project_name = pending_availability.get("project_name")
                if not item.currency:
                    item.currency = pending_availability.get("currency")
                if not item.file_format:
                    item.file_format = pending_availability.get("file_format")
                # For short follow-ups, explicitly prioritize the new value.
                value = message.strip().lower()
                if len(value) == 3 and value.isalpha():
                    item.currency = value.upper()
                if value in {"pdf", "excel", "xls", "xlsx", "spreadsheet", "pdf instead", "excel instead"}:
                    item.file_format = "pdf" if value.startswith("pdf") else "excel"
                missing = set(item.missing_fields)
                if item.project_id or item.project_name:
                    missing -= {"project_name", "project_identifier"}
                if item.currency:
                    missing.discard("currency")
                if item.file_format:
                    missing.discard("file_format")
                item.missing_fields = sorted(missing)
                item.requires_clarification = bool(missing)
        elif pending_availability and not availability_followup:
            # A distinct request supersedes the pending download.
            await availability_state.clear(user_id=user_id, session_id=str(session_id))
            pending_availability = None

        pending_sales_offer = await SalesOfferState(
            clients.redis
        ).load(
            user_id=user_id,
            session_id=str(session_id),
        )

        selected_sales_offer_names = [
            name.strip()
            for name in (selected_payment_plan_names or [])
            if isinstance(name, str) and name.strip()
        ]

        sales_intent = next(
            (
                item
                for item in routing_result.intents
                if item.intent == "sales_offer"
            ),
            None,
        )

        if selected_sales_offer_names and pending_sales_offer:

            if sales_intent is None:
                sales_intent = routing_result.intents[0].model_copy(
                    deep=True
                )
                sales_intent.intent = "sales_offer"
                routing_result.intents = [sales_intent]

            sales_intent.unit_id = pending_sales_offer.get("unit_id")
            sales_intent.unit_name = pending_sales_offer.get("unit_name")
            sales_intent.currency = pending_sales_offer.get("currency")

            sales_intent.project_name = None
            sales_intent.project_id = None
            sales_intent.project_number = None

            sales_intent.missing_fields = []
            sales_intent.requires_clarification = False
            routing_result.requires_clarification = False

            logger.info(
                "SALES_OFFER_CHECKBOX_CONTINUATION | "
                "session_id=%s | selected_count=%s",
                session_id,
                len(selected_sales_offer_names),
            )

        elif pending_sales_offer and sales_intent:
            selected_numbers = sales_intent.payment_plan_numbers or []

            if selected_numbers:
                sales_intent.unit_id = pending_sales_offer.get("unit_id")
                sales_intent.unit_name = pending_sales_offer.get("unit_name")
                sales_intent.currency = pending_sales_offer.get("currency")

                sales_intent.project_name = None
                sales_intent.project_id = None
                sales_intent.project_number = None

                sales_intent.missing_fields = []
                sales_intent.requires_clarification = False
                routing_result.requires_clarification = False

        for intent in routing_result.intents:

            if intent.intent != "inventory":
                continue

            if not previous_inventory_context:
                continue

            if intent.inventory_scope != "units":
                continue

            if intent.inventory_operation == "unit_comparison":

                previous_unit_numbers = previous_inventory_context.get(
                    "unit_numbers", []
                )

                if (
                    len(intent.compare_unit_numbers or []) < 2
                    and len(previous_unit_numbers) == 2
                ):

                    intent.compare_unit_numbers = list(
                        previous_unit_numbers
                    )

                    if not intent.project_name:
                        intent.project_name = (
                            previous_inventory_context.get("project_name")
                        )

                    resolved_fields = {"compare_unit_numbers"}

                    if intent.project_name:
                        resolved_fields.add("project_name")

                    intent.missing_fields = [
                        field
                        for field in intent.missing_fields
                        if field not in resolved_fields
                    ]

                    intent.requires_clarification = bool(
                        intent.missing_fields
                    )
                    

        for intent in routing_result.intents:

            if intent.intent != "inventory":
                continue

            if intent.inventory_operation != "payment_plan":
                continue

            if not previous_inventory_context:
                continue

            previous_project = (
                previous_inventory_context.get("project_name")
            )

            if (
                intent.project_name
                and previous_project
                and normalize_project_name(intent.project_name)
                != normalize_project_name(previous_project)
            ):
                continue

            resolved_unit = resolve_unit_from_previous_context(
                requested_unit=intent.unit_number,
                previous_context=previous_inventory_context,
            )

            if not resolved_unit:
                continue

            logger.info(
                "PAYMENT_PLAN_CONTEXT_RESOLVED | unit=%s",
                resolved_unit,
            )

            intent.unit_number = resolved_unit
            intent.inventory_scope = "units"

            if not intent.project_name and previous_project:
                intent.project_name = previous_project

            intent.missing_fields = [
                field
                for field in intent.missing_fields
                if field not in {
                    "unit_number",
                    "unit_identifier",
                }
            ]

            intent.requires_clarification = bool(
                intent.missing_fields
            )


        marketing_names = set(available_projects)

        inventory_active_names = set(
            inventory_catalogs.active_projects
        )

        inventory_unit_names = set(
            inventory_catalogs.unit_projects
        )

        # Map normalized marketing names to canonical names.
        marketing_name_lookup = {}

        for name in available_projects:
            key = normalize_project_name(name)
            marketing_name_lookup.setdefault(key, []).append(name)

        def resolve_visible_unit_project(user_message: str):
            matches = []

            for unit in inventory_snapshot.units:
                identifiers = [
                    unit.unit_id,
                    unit.unit_name,
                ]

                for identifier in identifiers:
                    if not identifier:
                        continue

                    pattern = (
                        r"(?<![A-Za-z0-9])"
                        + re.escape(str(identifier))
                        + r"(?![A-Za-z0-9])"
                    )

                    if re.search(
                        pattern,
                        user_message,
                        flags=re.IGNORECASE,
                    ):
                        matches.append(unit)
                        break

            unique_projects = {
                normalize_project_name(unit.project_name)
                for unit in matches
                if unit.project_name
            }

            if len(unique_projects) != 1:
                return None

            return matches[0].project_name
        

        # Tracks intents that must not execute.
        availability_denied = set()
        availability_access = DownloadAvailabilityAccessService(walkthrough_engine)
        blocked_intents = set()

        for index, intent in enumerate(routing_result.intents):
            if intent.intent == "download_availability":
                allowed, reason = availability_access.check(
                    role=role, source=source, employee_type=employee_type,
                )
                if not allowed:
                    availability_denied.add(index)
                    blocked_intents.add(index)
                    await availability_state.clear(
                        user_id=user_id, session_id=str(session_id),
                    )
                    logger.info(
                        "AVAILABILITY_ACCESS_DENIED | reason=%s | correlation_id=%s",
                        reason, correlation_id,
                    )

        for index, intent in enumerate(routing_result.intents):

            if index in availability_denied:
                continue

            # CENTRAL_PROJECT_RESOLUTION: catalog-scoped, zero extra LLM calls.
            # Only project-name matching is corrected. Feature-specific IDs,
            # account filters, and user permissions remain unchanged.
            if intent.intent in {
                "marketing", "bank_details", "inventory",
                "download_availability", "project_information", "sales_offer",
            } and not (
                intent.intent == "inventory"
                and intent.inventory_operation == "project_comparison"
            ) and not (
                intent.intent == "project_information"
                and intent.project_operation in {"latest", "list", "location_search"}
            ) and not (
                intent.intent == "marketing" and intent.action == "company_profile"
            ):
                if intent.intent == "marketing":
                    allowed_projects = marketing_names
                elif intent.intent == "bank_details":
                    allowed_projects = inventory_active_names
                elif intent.intent == "inventory":
                    allowed_projects = (
                        inventory_active_names
                        if intent.inventory_scope == "projects"
                        else inventory_active_names | inventory_unit_names
                    )
                else:
                    allowed_projects = inventory_active_names | inventory_unit_names

                match = resolve_project(
                    reference=intent.project_name,
                    message=message,
                    projects=allowed_projects,
                    require_message_mention=(intent.intent == "bank_details"),
                )

                original_llm_project = intent.project_name


                if match.status == "matched":
                    intent.project_name = match.name
                    intent.missing_fields = [
                        field for field in intent.missing_fields
                        if field not in {"project_name", "project_identifier"}
                    ]
                    intent.requires_clarification = bool(intent.missing_fields)
                    logger.info(
                        "PROJECT_RESOLUTION | intent=%s | method=%s",
                        intent.intent, match.method,
                    )
                elif match.status == "ambiguous":
                    intent.project_name = None
                    intent.requires_clarification = True
                    if "project_name" not in intent.missing_fields:
                        intent.missing_fields.append("project_name")
                    blocked_intents.add(index)
                elif intent.intent == "bank_details":
                    # A unit ID or LLM guess alone is insufficient for bank details.
                    intent.project_name = None
                    intent.requires_clarification = True
                    if "project_name" not in intent.missing_fields:
                        intent.missing_fields.append("project_name")
                    blocked_intents.add(index)

            if intent.intent == "marketing":
                
                resolved_project = resolve_visible_unit_project(
                    message
                )

                if resolved_project:
                    intent.project_name = resolved_project

                if intent.project_name:

                    key = normalize_project_name(
                        intent.project_name
                    )

                    candidates = marketing_name_lookup.get(
                        key, []
                    )

                    if len(candidates) == 1:
                        intent.project_name = candidates[0]

                        intent.missing_fields = [
                            field
                            for field in intent.missing_fields
                            if field != "project_name"
                        ]

                        intent.requires_clarification = bool(
                            intent.missing_fields
                        )

                    elif len(candidates) > 1:
                        intent.requires_clarification = True

                        if "project_name" not in intent.missing_fields:
                            intent.missing_fields.append(
                                "project_name"
                            )

                valid_names = marketing_names

            elif intent.intent == "inventory":
                if intent.inventory_operation == "project_comparison":

                    resolved_names = []
                    invalid_names = []

                    for requested_name in (
                        intent.compare_project_names or []
                    ):
                        comparison_match = match_project_reference(
                            requested_name,
                            inventory_active_names,
                        )
                        if comparison_match.status == "matched":
                            resolved_names.append(comparison_match.name)
                        else:
                            invalid_names.append(requested_name)

                    intent.compare_project_names = resolved_names

                    intent.missing_fields = [
                        field
                        for field in intent.missing_fields
                        if field not in {
                            "project_name",
                            "project_identifier",
                            "compare_project_names",
                            "compare_unit_numbers",
                        }
                    ]

                    if (
                        len(resolved_names) != 2
                        or len(set(resolved_names)) != 2
                        or invalid_names
                    ):
                        intent.missing_fields.append(
                            "compare_project_names"
                        )

                    intent.requires_clarification = bool(
                        intent.missing_fields
                    )

                    if intent.requires_clarification:
                        blocked_intents.add(index)

                    continue

                if intent.inventory_scope == "projects":
                    valid_names = inventory_active_names

                elif intent.inventory_scope == "units":
                    valid_names = (
                        inventory_active_names
                        | inventory_unit_names
                    )

                else:
                    intent.requires_clarification = True
                    blocked_intents.add(index)
                    continue

            elif intent.intent == "project_information":
                valid_names = set()

                if intent.project_operation in {
                    "latest",
                    "list",
                    "location_search",
                }:
                    intent.missing_fields = [
                        field
                        for field in intent.missing_fields
                        if field not in {
                            "project_name",
                            "project_identifier",
                        }
                    ]

                    intent.requires_clarification = bool(
                        intent.missing_fields
                    )

                # Resolve identifiers in ProjectInformationHandler.
                # Skip the old marketing-name validation.
                if intent.requires_clarification:
                    blocked_intents.add(index)

                continue


            elif intent.intent == "bank_details":
                valid_names = inventory_active_names

            elif intent.intent in {"download_availability", "sales_offer"}:
                valid_names = (
                    inventory_active_names
                    | inventory_unit_names
                )

            else:
                valid_names = marketing_names

            if intent.project_name is not None:

                normalized_requested = normalize_project_name(
                    intent.project_name
                )

                matches = [
                    name
                    for name in valid_names
                    if normalize_project_name(name)
                    == normalized_requested
                ]

                if len(matches) == 1:
                    intent.project_name = matches[0]

                    # Remove stale project-name clarification.
                    intent.missing_fields = [
                        field
                        for field in intent.missing_fields
                        if field != "project_name"
                    ]

                    if not intent.missing_fields:
                        intent.requires_clarification = False

                elif len(matches) == 0:
                    intent.requires_clarification = True
                    blocked_intents.add(index)

                    if "project_name" not in intent.missing_fields:
                        intent.missing_fields.append("project_name")

                else:
                    # Multiple catalog entries match the same normalized name.
                    # Do not guess which project was intended.
                    intent.requires_clarification = True
                    blocked_intents.add(index)

                    if "project_name" not in intent.missing_fields:
                        intent.missing_fields.append("project_name")

            if intent.intent == "download_availability":

                if index not in blocked_intents:

                    try:
                        resolved = resolve_availability_project(
                            intent=intent,
                            snapshot=inventory_snapshot,
                        )

                        intent.project_id = resolved.project_id
                        intent.project_name = resolved.project_name

                        intent.missing_fields = [
                            field
                            for field in intent.missing_fields
                            if field not in {
                                "project_name",
                                "project_identifier",
                            }
                        ]

                        intent.requires_clarification = bool(
                            intent.missing_fields
                        )

                    except AvailabilityResolutionError as exc:

                        intent.requires_clarification = True
                        blocked_intents.add(index)

                        logger.info(
                            "AVAILABILITY_RESOLUTION_FAILED | "
                            "reason=%s | correlation_id=%s",
                            str(exc),
                            correlation_id,
                        )


            if intent.intent == "download_availability" and index not in availability_denied:
                # Ensure all required fields are checked after project resolution.
                missing = set(intent.missing_fields)
                if not intent.project_id:
                    missing.add("project_identifier")
                else:
                    missing -= {"project_identifier", "project_name"}
                if not intent.currency:
                    missing.add("currency")
                else:
                    missing.discard("currency")
                if not intent.file_format:
                    missing.add("file_format")
                else:
                    missing.discard("file_format")
                intent.missing_fields = sorted(missing)
                intent.requires_clarification = bool(missing)
                if intent.requires_clarification:
                    await availability_state.save(
                        user_id=user_id,
                        session_id=str(session_id),
                        state={
                            "intent": "download_availability",
                            "project_id": intent.project_id,
                            "project_name": intent.project_name,
                            "currency": intent.currency,
                            "file_format": intent.file_format,
                        },
                    )

            # Block ambiguous or incomplete requests.
            if intent.requires_clarification:
                blocked_intents.add(index)

        routing_result.requires_clarification = any(
            item.requires_clarification
            for item in routing_result.intents
        )


        detected_intents = [
            item.intent
            for item in routing_result.intents
        ]

        generation_service = GenerationService(
            client=clients.foundry_openai,
            model=(
                settings.generation_openai_model
                or settings.foundry_openai_model
            ),
        )


        # GREETING INTENT — return fixed response without LLM 2
        if (
            len(routing_result.intents) == 1
            and routing_result.intents[0].intent == "greeting"
        ):
            greeting_response = ChatResponse(
                response=GREETING_RESPONSE,
                session_id=session_id,
                correlation_id=correlation_id,
                followups=[],
                data={
                    "files": [],
                    "classification": routing_result.model_dump(mode="json"),
                },
            )

            response_payload = {
                "version": 1,
                "html_blocks": [],
                "files": [],
                "followups": [],
                "inventory_context": None,
            }

            await persist_completed_chat(
                clients=clients,
                session_id=session_id,
                user_id=user_id,
                user_message=message,
                assistant_message=GREETING_RESPONSE,
                intents=["greeting"],
                latency_ms=int((time.perf_counter() - started_at) * 1000),
                response_payload=response_payload,
            )

            yield format_sse("token", {"text": GREETING_RESPONSE})
            yield format_sse("followups", {"chips": []})
            yield format_sse(
                "final",
                greeting_response.model_dump(mode="json"),
            )

            status = "completed"
            yield format_sse("done", {"status": status})
            return

        # 3. INITIALIZE INTENT DISPATCHER

        dispatcher = IntentDispatcher(
            redis_client=clients.redis,
            inventory_snapshot=inventory_snapshot,
            payment_client=inventory_client,
            payment_token=access_token,
            user_id=user_id,
            session_id=str(session_id),
            access_token=access_token,
            inventory_token=inventory_token,
            message=message,
            walkthrough_engine=walkthrough_engine,
            role=role,
            source=source,
            employee_type=employee_type,
            selected_payment_plan_names=selected_payment_plan_names,
        )

        handler_results = []
        clarification_messages = []

        # 4. PROCESS CLASSIFIED INTENTS

        for index, intent in enumerate(routing_result.intents):

            # FIX 3: Do not execute unresolved intents.
            if index in blocked_intents:

                if index in availability_denied:
                    clarification_messages.append(
                        "Download Availability is not available for your account."
                    )
                    continue
                if (
                    intent.intent == "sales_offer"
                    and pending_sales_offer
                    and selected_sales_offer_names
                ):
                    intent.missing_fields = []
                    intent.requires_clarification = False
                    continue

                if intent.intent == "download_availability":
                    missing = set(intent.missing_fields)
                    if "project_identifier" in missing or "project_name" in missing:
                        clarification_messages.append(
                            "Which Danube project would you like the availability report for?"
                        )
                    elif "currency" in missing:
                        clarification_messages.append(
                            "Which currency would you like for the availability report?"
                        )
                    elif "file_format" in missing:
                        clarification_messages.append(
                            "Would you like the report in PDF or Excel format?"
                        )
                    else:
                        clarification_messages.append(
                            "Please clarify the availability report details."
                        )
                    continue

                if intent.intent == "bank_details":
                    clarification_messages.append(
                        "Could you please tell me the project name "
                        "so I can share the bank details?"
                    )
                elif (
                    intent.intent == "inventory"
                    and intent.inventory_operation
                        == "project_comparison"
                ):
                    clarification_messages.append(
                        "Please provide two valid Danube "
                        "project names to compare."
                    )
                else:
                    clarification_messages.append(
                        "Please clarify the project or "
                        "details for your request."
                    )

                continue

            result = await dispatcher.execute(intent)

            if intent.intent == "download_availability" and result.has_data:
                await availability_state.clear(
                    user_id=user_id, session_id=str(session_id),
                )

            handler_results.append(result)

            logger.info(
                "INTENT_EXECUTED | "
                "correlation_id=%s | "
                "intent=%s | "
                "has_data=%s | "
                "html_blocks=%s",
                correlation_id,
                intent.intent,
                result.has_data,
                len(result.html_blocks),
            )


        # 4A. COMBINE HANDLER RESULTS

        all_html_blocks = []
        all_files = []
        response_messages = list(clarification_messages)
        generation_contexts = []

        for result in handler_results:

            all_html_blocks.extend(
                result.html_blocks
            )

            all_files.extend(
                result.files
            )

            response_messages.extend(
                result.messages
            )

            if result.has_data:
                generation_contexts.append(
                    result.generation_context
                )
                logger.info(
                    "GENERATION_CONTEXT_READY | "
                    "service=%s | operation=%s | match_status=%s",
                    result.generation_context.get("service"),
                    result.generation_context.get("operation"),
                    result.generation_context.get("match_status"),
                )


        # 5. BUILD RESPONSE USING LLM 2

        project_details_html_only = (
            len(routing_result.intents) == 1
            and len(handler_results) == 1
            and handler_results[0].intent == "project_information"
            and handler_results[0].has_data
            and handler_results[0].generation_context.get("operation")
                == "details"
            and not clarification_messages
            and any(
                block.get("card_type") == "project_details"
                for block in all_html_blocks
            )
        )

        inventory_html_only = (
            len(routing_result.intents) == 1
            and routing_result.intents[0].intent == "inventory"
            and routing_result.intents[0].inventory_operation
                in {"unit_search", "unit_comparison", "project_comparison"}
            and not clarification_messages
            and any(
                block.get("card_type") in {
                    "inventory_listing",
                    "inventory_comparison",
                }
                for block in all_html_blocks
            )
            and all(
                context.get("match_status") not in {
                    "partial",
                    "none",
                    "no_exact_matches",
                }
                for context in generation_contexts
            )
        )

        llm2_used = False
        real_llm_streaming = False
        streamed_answer = ""

        sales_offer_only = (
            len(routing_result.intents) == 1
            and routing_result.intents[0].intent == "sales_offer"
            and len(handler_results) == 1
            and handler_results[0].intent == "sales_offer"
            and not clarification_messages
        )

        if sales_offer_only:
            # The handler knows the actual workflow state and generated files.
            # Never ask LLM2 to invent a second unit-confirmation question.
            response_text = " ".join(response_messages).strip()
            followup_chips = []
            real_llm_streaming = False

        elif project_details_html_only:
            response_text = ""
            followup_chips = []
            real_llm_streaming = False


        elif generation_contexts:

            # Preserve the existing single-intent context.
            if len(generation_contexts) == 1:
                generation_context = generation_contexts[0]
            else:
                # Supports multiple successful intents.
                generation_context = {
                    "service": "multi_intent",
                    "results": generation_contexts,
                }

            # LLM 2 still runs for dynamic follow-up chips.
                        # Keep the original approved Excel steps as a safe fallback.
            walkthrough_only = (
                len(routing_result.intents) == 1
                and routing_result.intents[0].intent == "excel_walkthrough"
                and generation_context.get("service") == "excel_walkthrough"
            )

            try:
                
                real_llm_streaming = (
                    is_real_streaming_enabled()
                    and bool(generation_contexts)
                    and not clarification_messages
                )

                if real_llm_streaming:
                    generation_result = None

                    async for event_type, value in (
                        generation_service.generate_stream(
                            message=message,
                            language=routing_result.language,
                            intents=detected_intents,
                            service_results=generation_context,
                            history=history,
                        )
                    ):
                        if event_type == "token":
                            streamed_answer += value

                            yield format_sse(
                                "token",
                                {"text": value},
                            )

                        elif event_type == "result":
                            generation_result = value

                    if generation_result is None:
                        raise ValueError(
                            "Streaming returned no final result"
                        )

                else:
                    generation_result = (
                        await generation_service.generate(
                            message=message,
                            language=routing_result.language,
                            intents=detected_intents,
                            service_results=generation_context,
                            history=history,
                        )
                    )

                llm2_used = True
                followup_chips = generation_result.followups
                response_text = (
                    generation_result.response or ""
                ).strip()

            except Exception:
                if not walkthrough_only:
                    raise

                # If partial text is already visible, do not
                # append a completely different fallback answer.
                if streamed_answer:
                    raise

                logger.exception(
                    "WALKTHROUGH_GENERATION_FALLBACK | "
                    "correlation_id=%s",
                    correlation_id,
                )

                response_text = generation_context["approved_steps"]
                followup_chips = []
                real_llm_streaming = False


            # Preserve clarification and other messages.
            if response_messages:
                response_text = " ".join(
                    [response_text, *response_messages]
                ).strip()
            if real_llm_streaming:
                remaining_text = response_text[len(streamed_answer):]

                if not response_text.startswith(streamed_answer):
                    raise ValueError(
                        "Final response differs from streamed response"
                    )

                if remaining_text:
                    yield format_sse(
                        "token",
                        {"text": remaining_text},
                    )
                    streamed_answer += remaining_text

        else:

            if response_messages:
                response_text = " ".join(response_messages)
            else:
                response_text = (
                    "I couldn't find the requested "
                    "information. Please try specifying "
                    "a Danube project and what you need."
                )

            followup_chips = []


        # 5.1 ENSURE SALES OFFER DISCLAIMER

        SALES_OFFER_DISCLAIMER = (
            "Disclaimer: Exchange rate applied is valid for today "
            "only and subject to change at the time of unit booking."
        )

        sales_offer_succeeded = any(
            result.intent == "sales_offer"
            and result.generation_context.get("generated") is True
            for result in handler_results
        )

        if sales_offer_succeeded:
            if SALES_OFFER_DISCLAIMER not in response_text:
                response_text = (
                    response_text.rstrip()
                    + "\n\n"
                    + SALES_OFFER_DISCLAIMER
                )

        # 5A. PREPARE TEXT FOR DATABASE PERSISTENCE

        display_response_text = response_text.strip()

        if project_details_html_only:
            display_response_text = ""

        # Ensure that the assistant message is never empty.
        elif not display_response_text:
            if all_html_blocks:
                display_response_text = (
                    "I found the requested information. "
                    "You can view the details below."
                )
            else:
                display_response_text = (
                    "I couldn't find the requested information."
                )

        if project_details_html_only:
            persist_response_text = (
                "Project details displayed in HTML card."
            )
            response_text = ""
            display_response_text = ""
        else:
            persist_response_text = display_response_text
            response_text = display_response_text

        if real_llm_streaming:
            if not response_text.startswith(streamed_answer):
                raise ValueError(
                    "Final response does not match streamed text"
                )

            remaining_text = response_text[len(streamed_answer):]

            if remaining_text:
                yield format_sse(
                    "token",
                    {"text": remaining_text},
                )

                streamed_answer += remaining_text

        # 6. BUILD FINAL RESPONSE

        final_response = ChatResponse(
            response=display_response_text,
            session_id=session_id,
            correlation_id=correlation_id,
            followups=followup_chips,
            data={
                "files": all_files,
                "classification": (
                    routing_result.model_dump(mode="json")
                ),
            },
        )

        # 7. SAVE TO POSTGRESQL FIRST

        saved_html_blocks = [
            HTMLBlockEvent(
                card_type=block["card_type"],
                html=block["html"],
            ).model_dump(mode="json")
            for block in all_html_blocks
        ]

        new_inventory_context = None
        for intent, result in zip(
            [
                intent
                for index, intent in enumerate(routing_result.intents)
                if index not in blocked_intents
            ],
            handler_results,
        ):
            candidate = build_inventory_context(
                intent=intent,
                handler_result=result,
                inventory_snapshot=inventory_snapshot,
            )

            if candidate:
                new_inventory_context = candidate

        response_payload = {
            "version": 1,
            "html_blocks": saved_html_blocks,
            "files": final_response.model_dump(mode="json")["data"]["files"],
            "followups": final_response.model_dump(mode="json")["followups"],
            "inventory_context": new_inventory_context,

        }

        
        latency_ms = int(
            (time.perf_counter() - started_at) * 1000
        )

        saved_records = await persist_completed_chat(
            clients=clients,
            session_id=session_id,
            user_id=user_id,
            user_message=message,
            assistant_message=persist_response_text,
            intents=detected_intents,
            latency_ms=latency_ms,
            response_payload=response_payload,
        )


        # 8. STREAM GENERATED RESPONSE TEXT

        if not real_llm_streaming and response_text.strip():
            for word in response_text.split(" "):
                yield format_sse(
                    "token",
                    {"text": word + " "},
                )

                await asyncio.sleep(0.02)

        # 9. STREAM HTML BLOCKS


        for block in all_html_blocks:

            html_event = HTMLBlockEvent(
                card_type=block["card_type"],
                html=block["html"],
            )

            yield format_sse(
                "html_block",
                html_event.model_dump(mode="json"),
            )

        # 10. FOLLOW-UP CHIPS

    
        yield format_sse(
            "followups",
            {"chips": followup_chips},
        )

        # 11. FINAL RESPONSE EVENT

        final_payload = final_response.model_dump(
            mode="json"
        )
        yield format_sse(
            "final",
            final_payload,
        )

        status = "completed"

        audit_event(
            "CHAT_COMPLETED",
            status="completed",
            latency_ms=round(
                (time.perf_counter() - started_at) * 1000,
                2,
            ),
        )

    except asyncio.CancelledError:
        raise


    except Exception as exc:

        logger.exception(
            "CHAT_PROCESSING_EXCEPTION | correlation_id=%s | session_id=%s",
            correlation_id,
            session_id,
        )

        import traceback

        from app.core.exceptions import AppException

        if isinstance(exc, AppException):
            error_code = exc.error_code
        else:
            error_code = "INTERNAL_SERVER_ERROR"

        audit_event(
            "CHAT_FAILED",
            level="ERROR",
            status="failed",
            error_type=type(exc).__name__,
            latency_ms=round(
                (time.perf_counter() - started_at) * 1000,
                2,
            ),
        )

        if error_code == "INVENTORY_RATE_LIMITED":
            response_code = "INVENTORY_RATE_LIMITED"
            user_message = (
                "The property information service is "
                "currently busy. Please try again shortly."
            )
            retryable = True

        elif error_code in {
            "AUTHENTICATION_ERROR",
            "INVENTORY_ACCESS_ERROR",
        }:
            response_code = "AUTHENTICATION_ERROR"
            user_message = (
                "Your session could not be authenticated "
                "for property information. Please sign in "
                "again or contact support if the issue continues."
            )
            retryable = False

        elif error_code in {
            "INVENTORY_UPSTREAM_ERROR",
            "INVENTORY_RESPONSE_ERROR",
        }:
            response_code = "UPSTREAM_SERVICE_ERROR"
            user_message = (
                "We couldn't retrieve the property information "
                "from Danube's service right now. "
                "Please try again later."
            )
            retryable = True

        elif error_code == "INVENTORY_CONFIGURATION_ERROR":
            response_code = "SERVICE_CONFIGURATION_ERROR"
            user_message = (
                "The property information service is "
                "not configured correctly. Please contact support."
            )
            retryable = False

        else:
            response_code = "INTERNAL_SERVER_ERROR"
            user_message = (
                "An unexpected error occurred while processing "
                "your request. Please try again later."
            )
            retryable = False

        error_response = ErrorResponse(
            error=ErrorDetail(
                code=response_code,
                message=user_message,
                session_id=str(session_id),
                correlation_id=correlation_id,
                retryable=retryable,
            )
        )

        yield format_sse(
            "error",
            error_response.model_dump(mode="json"),
        )

    # 12. DONE EVENT

    yield format_sse(
        "done",
        {
            "status": status,
        },
    )

async def stream_chat_response(
    message: str,
    session_id: uuid.UUID,
    correlation_id: str,
    user_id: str,
    role: str,
    source: str,
    employee_type: str,
    clients: ServiceClients,
    access_token: str,
    walkthrough_engine: WalkthroughEngine,
    selected_payment_plan_names: list[str] | None = None,
):
    started_at = time.perf_counter()

    log_token = log_context.set({
        "correlation_id": correlation_id,
        "session_id": str(session_id),
    })

    status = "failed"

    try:
        async for event in _stream_chat_response_impl(
            message=message,
            session_id=session_id,
            correlation_id=correlation_id,
            user_id=user_id,
            role=role,
            source=source,
            employee_type=employee_type,
            clients=clients,
            access_token=access_token,
            walkthrough_engine=walkthrough_engine,
            selected_payment_plan_names=selected_payment_plan_names,
        ):
            if event.startswith("event: done\n"):
                if '"completed"' in event:
                    status = "completed"

            yield event

    except asyncio.CancelledError:
        status = "cancelled"
        raise

    except Exception as exc:
        audit_event(
            "CHAT_STREAM_WRAPPER_FAILED",
            level="ERROR",
            status="failed",
            error_type=type(exc).__name__,
        )
        raise

    finally:
        audit_event(
            "CHAT_PROCESSING_COMPLETED",
            status=status,
            latency_ms=round(
                (time.perf_counter() - started_at) * 1000,
                2,
            ),
        )

        log_context.reset(log_token)