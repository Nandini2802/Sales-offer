import logging
import asyncio


from app.schemas.handler_result import HandlerResult
from app.schemas.retrieval import InventorySnapshot
from app.services.inventory_filter_service import (
    InventoryFilterService,
    norm,
)
from app.services.template_service import TemplateService
from app.handlers.payment_plan_handler import PaymentPlanHandler
from app.services.project_name_service import normalize_project_name
from app.services.unit_comparison_client import UnitComparisonClient
from app.services.unit_comparison_mapper import map_comparison
from app.handlers.payment_plan_handler import PaymentPlanHandler

logger = logging.getLogger(__name__)


class InventoryHandler:

    MAX_DISPLAY_UNITS = 20

    def __init__(
        self,
        snapshot: InventorySnapshot,
        payment_client=None,
        payment_token: str | None = None,
        user_id: str | None = None,
    ):
        self.snapshot = snapshot
        self.payment_client = payment_client
        self.payment_token = payment_token
        self.user_id = user_id
        self.filter_service = InventoryFilterService()
        self.template_service = TemplateService()
        self.unit_comparison_client = UnitComparisonClient()

    async def handle(self, intent) -> HandlerResult:

        result = HandlerResult(intent="inventory")

        operation = intent.inventory_operation

        if operation == "project_comparison":
            return self._handle_project_comparison(intent, result)

        # Project-level inventory
        if (
            intent.intent == "project_information"
            or intent.inventory_scope == "projects"
        ):
            return self._handle_projects(intent, result)

        if intent.inventory_scope != "units":
            result.messages.append(
                "Please specify whether you want "
                "project information or unit details."
            )
            return result

        # Unit comparison
        if operation == "unit_comparison":
            return await self._handle_comparison(intent, result)

        # Unit search / details
        if operation == "unit_details" and intent.unit_number:

            requested = norm(intent.unit_number)

            matches = [
                unit
                for unit in self.snapshot.units
                if requested in {
                    norm(unit.unit_name),
                    norm(unit.unit_code),
                    norm(unit.unit_id),
                }
                and (
                    not intent.project_name
                    or normalize_project_name(unit.project_name or "")
                    == normalize_project_name(intent.project_name)
                )
            ]

        else:
            matches = self.filter_service.filter_units(
                units=self.snapshot.units,
                intent=intent,
            )

        if not matches:

            related_units = [
                unit
                for unit in self.snapshot.units
                if (
                    not intent.project_name
                    or normalize_project_name(unit.project_name or "")
                    == normalize_project_name(intent.project_name)
                )
            ]

            result.generation_context = {
                "service": "inventory",
                "operation": operation or "unit_search",
                "match_status": "no_exact_matches",
                "requested_project": intent.project_name,
                "exact_matches": [],
                "related_units": [
                    self._unit_data(unit)
                    for unit in related_units[:5]
                ],
                "related_units_are_not_exact_matches": True,
            }

            result.has_data = True
            return result

        # Unit details require exactly one match.
        if operation == "unit_details" and len(matches) != 1:
            result.messages.append(
                "Multiple units match this identifier. "
                "Please specify the project and exact unit."
            )
            return result

        # Limit the number of displayed units.
        displayed = matches[:self.MAX_DISPLAY_UNITS]

        safe_units = [
            self._unit_data(unit)
            for unit in displayed
        ]

        # STEP 2: Enrich unit details using Active Projects API data.
        if operation == "unit_details" and len(matches) == 1:

            unit = matches[0]

            # Match the project using Salesforce project ID.
            project = next(
                (
                    p for p in self.snapshot.projects
                    if (
                        unit.project_id
                        and p.project_id == unit.project_id
                    )
                ),
                None,
            )

            # Fall back to project-name matching.
            if project is None:
                project = next(
                    (
                        p for p in self.snapshot.projects
                        if normalize_project_name(p.project_name)
                        == normalize_project_name(unit.project_name or "")
                    ),
                    None,
                )

            # Enrich the unit using its matched Active Projects record.
            safe_units[0]["project_information"] = (
                self._project_data(project) if project else None
            )

            logger.debug(
                "INVENTORY_CROSS_API_MATCH | unit=%s | matched=%s",
                unit.unit_name,
                project.project_name if project else None,
            )

        result.generation_context = {
            "service": "inventory",
            "operation": operation or "unit_search",
            "project": intent.project_name,
            "total_matches": len(matches),
            "displayed_count": len(displayed),
            "units": safe_units,
        }

        if operation != "unit_details":

            result.html_blocks.append({
                "card_type": "inventory_listing",
                "html": self.template_service.render(
                    "listing 2.html.j2",
                    units=safe_units,
                    total_matches=len(matches),
                ),
            })

        result.has_data = True

        return result

    def _handle_projects(self, intent, result):
        projects = self.snapshot.projects

        if intent.project_name:

            requested = normalize_project_name(
                intent.project_name
            )

            projects = [
                project
                for project in projects
                if normalize_project_name(project.project_name or "")
                == requested
            ]

        if not projects:
            result.messages.append(
                "No matching active project information was found."
            )
            return result

        safe_projects = [
            self._project_data(project)
            for project in projects[:20]
        ]

        result.generation_context = {
            "service": "inventory",
            "operation": "project_info",
            "projects": safe_projects,
            "total_matches": len(projects),
        }

        result.has_data = True

        return result

    async def _handle_comparison(self, intent, result):

        identifiers = intent.compare_unit_numbers or []

        if len(identifiers) != 2:
            result.messages.append(
                "Please provide exactly two units to compare."
            )
            return result

        candidates = self.snapshot.units

        if intent.project_name:
            candidates = [
                unit for unit in candidates
                if norm(unit.project_name)
                == norm(intent.project_name)
            ]

        selected = []
        selected_keys = set()

        for identifier in identifiers:

            matches = [
                unit for unit in candidates
                if norm(identifier) in {
                    norm(unit.unit_name),
                    norm(unit.unit_code),
                }
            ]

            if len(matches) != 1:
                result.messages.append(
                    f"Could not uniquely identify unit "
                    f"{identifier} in your visible inventory. "
                    "Please specify its project and unit number."
                )
                return result

            unit = matches[0]
            key = (
                norm(unit.project_name),
                norm(unit.unit_id or unit.unit_name),
            )

            if key in selected_keys:
                result.messages.append(
                    "Please select different units to compare."
                )
                return result

            selected_keys.add(key)
            selected.append(unit)


        if not self.payment_token or not self.user_id:
            result.messages.append(
                "Authentication is required to compare units."
            )
            return result

        if not all(
            unit.unit_id and unit.project_id
            for unit in selected
        ):
            result.messages.append(
                "Unable to identify the selected units."
            )
            return result

        try:
            api_data = await self.unit_comparison_client.compare_units(
                token=self.payment_token,
                user_id=self.user_id,
                project_ids=[
                    unit.project_id for unit in selected
                ],
                unit_ids=[
                    unit.unit_id for unit in selected
                ],
            )

        except Exception:
            logger.exception("UNIT_COMPARISON_API_ERROR")
            result.messages.append(
                "Unable to compare units right now. "
                "Please try again."
            )
            return result

        # Map each returned unit to its parent project.
        api_units = {}

        for project in api_data:
            if not isinstance(project, dict):
                continue

            project_id = project.get("Id")

            records = (
                (project.get("UnitsProject__r") or {})
                .get("records") or []
            )

            for record in records:
                if not isinstance(record, dict):
                    continue

                unit_id = record.get("Id")

                if not unit_id:
                    continue

                # Ensure each returned unit belongs to its
                # declared project.
                if record.get("Project__c") != project_id:
                    continue

                api_units[unit_id] = {
                    "project": project,
                    "unit": record,
                }

        comparisons = []

        for selected_unit in selected:

            matched = api_units.get(selected_unit.unit_id)

            if not matched:
                result.messages.append(
                    "Comparison data is unavailable for "
                    "one or more selected units."
                )
                return result

            if (
                matched["project"].get("Id")
                != selected_unit.project_id
            ):
                result.messages.append(
                    "The returned project information "
                    "does not match the selected unit."
                )
                return result

            comparisons.append(
                map_comparison(
                    matched["project"],
                    matched["unit"],
                )
            )

            if self.payment_client and self.payment_token and self.user_id:

                async def fetch_payment_schedules(unit):
                    try:
                        return await self.payment_client.get_payment_plans(
                            token=self.payment_token,
                            user_id=self.user_id,
                            unit_id=unit.unit_id,
                        )
                    except Exception:
                        logger.exception(
                            "COMPARISON_PAYMENT_SCHEDULE_FETCH_FAILED"
                        )
                        return None

                payment_results = await asyncio.gather(
                    *(
                        fetch_payment_schedules(unit)
                        for unit in selected
                    )
                )

                for index, payment_result in enumerate(payment_results):

                    if index >= len(comparisons):
                        logger.warning(
                            "PAYMENT_RESULT_SKIPPED | index=%s | comparisons=%s",
                            index,
                            len(comparisons),
                        )
                        continue

                    comparison = comparisons[index]
                    selected_unit = selected[index]

                    for plan in comparison["payment_plans"]:

                        plan["schedule"] = None

                        matched_plan = next(
                            (
                                item
                                for item in payment_result
                                if isinstance(item, dict)
                                and str(item.get("Name", "")).strip().casefold()
                                == str(plan["name"]).strip().casefold()
                            ),
                            None,
                        )

                        if not matched_plan:
                            continue

                        try:
                            plan["schedule"] = (
                                PaymentPlanHandler._normalize_installments(
                                    matched_plan,
                                    selected_unit,
                                )
                            )

                        except ValueError:
                            logger.warning(
                                "COMPARISON_INSTALLMENT_NORMALIZATION_FAILED"
                            )


        result.generation_context = {
            "service": "inventory",
            "operation": "unit_comparison",
            "comparisons": [
                {
                    "unit": item["unit"],
                    "payment_plan_count": len(
                        item["payment_plans"]
                    ),
                }
                for item in comparisons
            ],
        }

        result.html_blocks.append({
            "card_type": "inventory_comparison",
            "html": self.template_service.render(
                "compare 2.html.j2",
                comparisons=comparisons,
                comparison_mode="units",
            ),
        })

        result.has_data = True
        return result

    def _handle_project_comparison(self, intent, result):
        """Compare exactly two projects from Active Projects API."""

        requested_names = intent.compare_project_names or []

        if len(requested_names) != 2:
            result.messages.append(
                "Please provide exactly two project names to compare."
            )
            return result

        selected_projects = []
        selected_keys = set()

        # Resolve both projects from the actual Active Projects snapshot.
        for name in requested_names:

            normalized_name = normalize_project_name(name)

            matches = [
                project
                for project in self.snapshot.projects
                if normalize_project_name(
                    project.project_name or ""
                ) == normalized_name
            ]

            if len(matches) != 1:
                result.messages.append(
                    f"Could not uniquely identify project '{name}'. "
                    "Please provide the exact project name."
                )
                return result

            if normalized_name in selected_keys:
                result.messages.append(
                    "Please select two different projects to compare."
                )
                return result

            selected_projects.append(matches[0])
            selected_keys.add(normalized_name)

        comparisons = []

        for project in selected_projects:

            # Reuse your existing Active Projects API field mapping.
            project_data = self._project_data(project)

            # Snapshot units are scoped to the authenticated user.
            visible_units = [
                unit
                for unit in self.snapshot.units
                if (
                    unit.project_id
                    and project.project_id
                    and str(unit.project_id)
                        == str(project.project_id)
                )
                or (
                    normalize_project_name(
                        unit.project_name or ""
                    ) == normalize_project_name(
                        project.project_name or ""
                    )
                )
            ]

            unit_types = sorted({
                str(unit.unit_type)
                for unit in visible_units
                if unit.unit_type is not None
                and str(unit.unit_type).strip()
            })

            bedroom_types = sorted({
                str(unit.bedrooms)
                for unit in visible_units
                if unit.bedrooms is not None
            })

            # Amenities can be a list or a string.
            raw_amenities = project.amenities

            if isinstance(raw_amenities, list):
                amenities = [
                    value.strip()
                    for value in raw_amenities
                    if isinstance(value, str) and value.strip()
                ]
            elif isinstance(raw_amenities, str):
                amenities = (
                    [raw_amenities.strip()]
                    if raw_amenities.strip()
                    else []
                )
            else:
                amenities = []

            comparisons.append({
                "project": project_data,
                "inventory": {
                    "visible_unit_count": len(visible_units),
                    "unit_types": unit_types,
                    "bedroom_types": bedroom_types,
                },
                "amenities": amenities,
            })

        # Only verified project/inventory data is sent to LLM 2.
        result.generation_context = {
            "service": "inventory",
            "operation": "project_comparison",
            "comparisons": comparisons,
        }

        # Reuse the same HTML template as Unit Comparison.
        result.html_blocks.append({
            "card_type": "inventory_comparison",
            "html": self.template_service.render(
                "compare-projects.html.j2",
                comparisons=comparisons,
                comparison_mode="projects",
            ),
        })

        result.has_data = True

        return result

    @staticmethod
    def _unit_data(unit):
        return {
            "project_name": unit.project_name,
            "project_code": unit.project_code,
            "project_location": unit.project_location,
            "unit_name": unit.unit_name,
            "unit_code": unit.unit_code,

            "building_name": unit.building_name,
            "building_code": unit.building_code,
            "floor_number": unit.floor_number,
            "floor_code": unit.floor_code,

            "category": unit.category,
            "typology": unit.typology,
            "unit_type": unit.unit_type,

            "bedrooms": unit.bedrooms,
            "bathrooms": unit.bathrooms,
            "parking_spaces": unit.parking_spaces,
            "internal_saleable_area": unit.internal_saleable_area,
            "area_sqft": unit.area_sqft,
            "plot_area": unit.plot_area,
            "view": unit.view,

            "price": unit.price,
            "currency": unit.currency,
            "status": unit.status,
            "handover_status": unit.handover_status,
            "construction_status": unit.construction_status,
            "is_show_villa": unit.is_show_villa,
        }

    @staticmethod
    def _project_data(project):
        """Verified business-facing fields from the Active Projects API.

        Preserve null, zero and false as supplied. Do not expose internal
        Salesforce IDs, feature flags, or potentially authenticated file URLs
        directly to the generation model.
        """
        return {
            "project_name": project.project_name,
            "project_number": project.project_number,
            "project_configuration": project.project_configuration,
            "project_web_id": project.project_web_id,
            "project_sequence": project.project_sequence,
            "location": project.location,
            "construction_status": project.construction_status,
            "handover_date": project.handover_date,
            "completion_date": project.completion_date,
            "service_charge": project.service_charge,
            "payment_plan": project.payment_plan,
            "starting_price": project.starting_price,
            "bedrooms_categories": project.bedrooms_categories,
            "apartments": project.apartments,
            "project_image": project.project_image,
            "unit_of_measurement": project.unit_of_measurement,
            "total_units": project.total_units,
            "total_sold_units": project.total_sold_units,
            "total_selling_price": project.total_selling_price,
            "total_saleable_area": project.total_saleable_area,
            "total_residential_units": project.total_residential_units,
            "total_other_units": project.total_other_units,
            "total_new_units": project.total_new_units,
            "total_floors": project.total_floors,
            "total_commercial_units": project.total_commercial_units,
            "total_buildings": project.total_buildings,
            "total_booked_units": project.total_booked_units,
            "total_bua_sqft": project.total_bua_sqft,
            "total_available_units": project.total_available_units,
            "total_available_residential_units": (
                project.total_available_residential_units
            ),
            "total_available_commercial_units": (
                project.total_available_commercial_units
            ),
            "plot_size_sqft": project.plot_size_sqft,
            "places_nearby": project.places_nearby,
            "building_type": project.building_type,
            "amenities": project.amenities,
            "eoi_active": project.eoi_active,
        }
