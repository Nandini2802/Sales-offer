import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.handler_result import HandlerResult
from app.schemas.retrieval import InventorySnapshot
from app.retrieval.salesforce_client import SalesforceClient
from app.services.template_service import TemplateService
from app.services.project_name_service import normalize_project_name

from app.services.payment_plan_context_service import (
    save_pending_payment_selection,
)

logger = logging.getLogger(__name__)


def first_value(record: dict, *keys, default=None):
    """Return the first nonempty value from known API fields."""
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return default


def as_decimal(value):
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value).replace(",", "").replace("%", ""))
    except (InvalidOperation, ValueError):
        return None


def format_number(value):
    number = as_decimal(value)

    if number is None:
        return None

    return f"{number:,.2f}"


def format_percent(value):
    number = as_decimal(value)

    if number is None:
        return "Not provided"

    return f"{number:g}%"


def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


class PaymentPlanHandler:

    def __init__(
        self,
        snapshot: InventorySnapshot,
        salesforce_client: SalesforceClient,
        token: str,
        user_id: str,
        redis_client,
        session_id: str,
    ):
        self.snapshot = snapshot
        self.salesforce_client = salesforce_client
        self.token = token
        self.user_id = user_id
        self.templates = TemplateService()
        self.redis_client = redis_client
        self.session_id = session_id

    def _resolve_units(self, intent):
        requested_unit = str(
            intent.unit_number or ""
        ).strip().casefold()

        requested_project = normalize_project_name(
            intent.project_name or ""
        )

        requested_number = str(
            getattr(intent, "project_number", None) or ""
        ).strip()

        if requested_unit:
            matches = [
                unit
                for unit in self.snapshot.units
                if requested_unit in {
                    str(unit.unit_id or "").strip().casefold(),
                    str(unit.unit_name or "").strip().casefold(),
                    str(unit.unit_code or "").strip().casefold(),
                }
            ]

            if requested_project:
                matches = [
                    unit for unit in matches
                    if normalize_project_name(
                        unit.project_name or ""
                    ) == requested_project
                ]

            if requested_number:
                project_ids = {
                    project.project_id
                    for project in self.snapshot.projects
                    if str(project.project_number or "").strip()
                    == requested_number
                }

                matches = [
                    unit for unit in matches
                    if unit.project_id in project_ids
                ]

            return matches

        projects = list(self.snapshot.projects)

        if requested_project:
            projects = [
                project
                for project in projects
                if normalize_project_name(
                    project.project_name or ""
                ) == requested_project
            ]

        if requested_number:
            projects = [
                project
                for project in projects
                if str(project.project_number or "").strip()
                == requested_number
            ]

        if not requested_project and not requested_number:
            return []

        project_ids = {
            project.project_id
            for project in projects
            if project.project_id
        }

        project_names = {
            normalize_project_name(project.project_name or "")
            for project in projects
            if project.project_name
        }

        return [
            unit
            for unit in self.snapshot.units
            if (
                (
                    unit.project_id is not None
                    and unit.project_id in project_ids
                )
                or (
                    unit.project_name
                    and normalize_project_name(
                        unit.project_name
                    ) in project_names
                )
            )
        ]

    @staticmethod
    def _plan_name(plan):
        return str(first_value(
            plan,
            "Name",
            "name",
            "Payment_Plan_Name__c",
            "paymentPlanName",
            default="Unnamed payment plan",
        ))

    @staticmethod
    def _installment_records(plan):
        """
        Extract installment records from the Payment Plan API.

        Actual Salesforce response:
        PaymentInstallments__r: {
            "totalSize": 4,
            "done": True,
            "records": [...]
        }
        """

        for key in (
            "PaymentInstallments__r",
            "installments",
            "Installments",
            "paymentPlanInstallments",
            "PaymentPlanInstallments",
            "Payment_Plan_Installments__r",
        ):
            records = plan.get(key)

            if isinstance(records, list):
                return records

            if isinstance(records, dict):
                nested = records.get("records")

                if isinstance(nested, list):
                    return nested

        return None


    @staticmethod
    def _normalize_installments(plan, unit):
        """
        Normalize the actual Salesforce Payment Plan response
        into data expected by payment 2.html.j2.
        """

        raw_records = PaymentPlanHandler._installment_records(plan)

        if raw_records is None:
            return None

        grouped = defaultdict(list)

        currency = str(
            first_value(
                plan,
                "CurrencyIsoCode",
                "currency",
                default=unit.currency or "AED",
            )
        )

        for index, record in enumerate(raw_records):

            if not isinstance(record, dict):
                raise ValueError(
                    "Invalid installment record returned by API"
                )

            # Actual API field: InstallmentDate__c
            raw_date = first_value(
                record,
                "InstallmentDate__c",
                "Due_Date__c",
                "Installment_Date__c",
                "Payment_Date__c",
                "dueDate",
                "date",
            )

            due_date = parse_date(raw_date)

            # Actual API field: InstallmentNumber__c
            installment_number = first_value(
                record,
                "InstallmentNumber__c",
                "installmentNumber",
                default=index + 1,
            )

            description = str(
                first_value(
                    record,
                    "Description__c",
                    "Milestone__c",
                    "Installment_Description__c",
                    "description",
                    "milestone",
                    default=f"Installment {installment_number}",
                )
            )

            # Actual API field: InstallmentPercentage__c
            percentage = first_value(
                record,
                "InstallmentPercentage__c",
                "Percentage__c",
                "Installment_Percentage__c",
                "Payment_Percentage__c",
                "percentage",
                "percent",
            )

            # The current API response does not contain amounts.
            amount = first_value(
                record,
                "Amount__c",
                "Installment_Amount__c",
                "amount",
            )

            formatted_amount = format_number(amount)

            year = (
                str(due_date.year)
                if due_date
                else "Undated"
            )

            grouped[year].append({
                "installment_number": installment_number,
                "display_date": (
                    due_date.strftime("%d %b %Y")
                    if due_date
                    else (
                        str(raw_date)
                        if raw_date
                        else "Date pending"
                    )
                ),
                "description": description,
                "display_percentage": format_percent(percentage),
                "display_amount": (
                    f"{currency} {formatted_amount}"
                    if formatted_amount is not None
                    else "Not provided"
                ),
                "installment_type": record.get(
                    "Installment_Type__c"
                ),
                "is_handover_payment": record.get(
                    "Is_Handover_Payment__c",
                    False,
                ),
                "sort_date": (
                    due_date.isoformat()
                    if due_date
                    else "9999-12-31"
                ),
                "sort_index": index,
            })

        for records in grouped.values():

            records.sort(
                key=lambda item: (
                    item["sort_date"],
                    item["sort_index"],
                )
            )

            for record in records:
                record.pop("sort_date", None)
                record.pop("sort_index", None)

        return dict(
            sorted(
                grouped.items(),
                key=lambda item: (
                    item[0] == "Undated",
                    item[0],
                ),
            )
        )


    async def handle(self, intent, selected_plan_id: str | None = None) -> HandlerResult:
        result = HandlerResult(intent="inventory")

        matches = self._resolve_units(intent)

        if not matches:
            result.messages.append(
                "I couldn't find an authorized unit for "
                "that project or unit identifier. "
                "Please check the details."
            )
            return result

        if len(matches) > 1:
            unit_names = sorted({
                unit.unit_name or unit.unit_id
                for unit in matches
                if unit.unit_name or unit.unit_id
            })

            preview = ", ".join(unit_names[:5])

            result.messages.append(
                "Multiple units match your request. "
                "Please specify the exact unit. "
                f"Matching units include: {preview}."
            )
            return result

        unit = matches[0]

        if not unit.unit_id:
            result.messages.append(
                "The selected unit does not have a "
                "Salesforce ID required for payment plans."
            )
            return result

        logger.info(
            "PAYMENT_PLAN_LOOKUP | user_id=%s | unit_id=%s",
            self.user_id,
            unit.unit_id,
        )

        plans = await self.salesforce_client.get_payment_plans(
            token=self.token,
            user_id=self.user_id,
            unit_id=unit.unit_id,
        )

        if not plans:
            result.messages.append(
                "No payment plans were returned for this unit."
            )
            return result

        

        # No implicit selection of a plan.
        if len(plans) > 1 and selected_plan_id is None:
            await save_pending_payment_selection(
                redis_client=self.redis_client,
                user_id=self.user_id,
                session_id=self.session_id,
                unit_id=unit.unit_id,
                unit_name=unit.unit_name,
                plans=plans,
            )

            plan_names = [
                plan["Name"]
                for plan in plans
                if plan.get("Name")
            ]

            numbered_options = "\n".join(
                f"{index}. {name}"
                for index, name in enumerate(plan_names, start=1)
            )

            return HandlerResult(
                intent="inventory",
                messages=[
                    f"I found {len(plan_names)} payment plans "
                    f"for {unit.unit_name}. "
                    "Please choose a plan by its number or name:\n"
                    f"{numbered_options}"
                ],
            )

        if selected_plan_id is not None:
            selected_matches = [
                item for item in plans
                if str(item.get("Id", "")) == str(selected_plan_id)
            ]
            if len(selected_matches) != 1:
                result.messages.append(
                    "That payment plan is no longer available for this unit. "
                    "Please request the payment plans again."
                )
                return result
            plan = selected_matches[0]
        else:
            plan = plans[0]

        try:
            installments_by_year = self._normalize_installments(
                plan,
                unit,
            )
        except ValueError:
            logger.exception(
                "PAYMENT_PLAN_INSTALLMENT_INVALID"
            )
            result.messages.append(
                "The payment schedule could not be displayed "
                "because the returned installment data is invalid."
            )
            return result

        if installments_by_year is None:
            result.messages.append(
                "The payment plan was found, but its "
                "installment schedule is not available "
                "in the expected response format."
            )
            return result

        plan_name = self._plan_name(plan)

        classification = first_value(
            plan,
            "Classification__c",
            "classification",
        )

        plan_type = first_value(
            plan,
            "PaymentPlanType__c",
            "Payment_Plan_Type__c",
            "paymentPlanType",
        )

        pre_handover = first_value(
            plan,
            "Pre_Handover_Percentage__c",
            "preHandoverPercentage",
        )

        post_handover = first_value(
            plan,
            "Post_Handover_Percentage__c",
            "postHandoverPercentage",
        )

        installment_count = sum(
            len(records)
            for records in installments_by_year.values()
        )

        html = self.templates.render(
            "payment 2.html.j2",
            project_name=unit.project_name or "Danube Property",
            unit_name=unit.unit_name or unit.unit_id,
            plan_name=plan_name,
            classification=classification,
            plan_type=plan_type,
            pre_handover=(
                format_percent(pre_handover)
                if pre_handover is not None else None
            ),
            post_handover=(
                format_percent(post_handover)
                if post_handover is not None else None
            ),
            installment_count=installment_count,
            installments_by_year=installments_by_year,
        )

        result.html_blocks.append({
            "card_type": "payment_plan",
            "html": html,
        })

        result.generation_context = {
            "service": "inventory",
            "operation": "payment_plan",
            "match_status": "exact",
            "project_name": unit.project_name,
            "unit_name": unit.unit_name,
            "payment_plan": {
                "name": plan_name,
                "classification": classification,
                "type": plan_type,
                "pre_handover_percentage": (
                    str(pre_handover)
                    if pre_handover is not None else None
                ),
                "post_handover_percentage": (
                    str(post_handover)
                    if post_handover is not None else None
                ),
                "installment_count": installment_count,
                "installments_by_year": installments_by_year,
            },
        }

        result.has_data = True

        return result
