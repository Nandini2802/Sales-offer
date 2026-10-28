import re

from app.services.project_name_service import normalize_project_name


def get_previous_inventory_context(response_payload: dict | None):
    if not isinstance(response_payload, dict):
        return None

    context = response_payload.get("inventory_context")

    if not isinstance(context, dict):
        return None

    if context.get("operation") not in {
        "unit_search",
        "unit_comparison",
        "unit_details",
    }:
        return None

    unit_ids = context.get("unit_ids", [])

    if not isinstance(unit_ids, list):
        return None

    return {
        "project_name": context.get("project_name"),
        "unit_ids": [str(uid) for uid in unit_ids if uid],
        "operation": context.get("operation"),
        "total_matches": context.get("total_matches", 0),
    }


def resolve_authorized_units(previous_context, inventory_snapshot):
    if not previous_context:
        return []

    allowed_ids = set(previous_context.get("unit_ids", []))

    return [
        unit
        for unit in inventory_snapshot.units
        if unit.unit_id and str(unit.unit_id) in allowed_ids
    ]


def build_inventory_context(intent, handler_result, inventory_snapshot):
    if not handler_result.has_data:
        return None

    context = handler_result.generation_context

    if context.get("service") != "inventory":
        return None

    operation = context.get("operation")

    if operation not in {
        "unit_search",
        "unit_comparison",
        "unit_details",
    }:
        return None

    unit_names = set()

    if operation == "unit_comparison":
        for comparison in context.get("comparisons", []):
            unit_name = comparison.get("unit", {}).get("unit_name")
            if unit_name:
                unit_names.add(unit_name)
    else:
        for unit in context.get("units", []):
            unit_name = unit.get("unit_name")
            if unit_name:
                unit_names.add(unit_name)

    selected_units = [
        unit
        for unit in inventory_snapshot.units
        if unit.unit_name in unit_names
        and (
            not intent.project_name
            or normalize_project_name(unit.project_name)
            == normalize_project_name(intent.project_name)
        )
    ]

    return {
        "project_name": intent.project_name,
        "unit_ids": [str(unit.unit_id) for unit in selected_units if unit.unit_id],
        "operation": operation,
        "total_matches": context.get("total_matches", len(selected_units)),
    }

def resolve_unit_from_previous_context(
    requested_unit: str | None,
    previous_context: dict | None,
) -> str | None:
    """
    Resolve a partial unit reference using previously
    compared units.

    Example:
        requested_unit = "808"
        previous units = ["GRZ-TH-808", "GRZ-TH-809"]

        returns "GRZ-TH-808"

    Returns None when there is no unique match.
    """

    if not requested_unit or not previous_context:
        return None

    previous_units = previous_context.get("unit_numbers") or []

    if not previous_units:
        return None

    requested = str(requested_unit).strip().casefold()

    # Allow "unit 808" as well as "808".
    requested = re.sub(
        r"^unit\s*(?:number\s*)?",
        "",
        requested,
    ).strip()

    if not requested:
        return None

    # First try exact full unit name.
    exact_matches = [
        unit_name
        for unit_name in previous_units
        if str(unit_name).strip().casefold() == requested
    ]

    if len(exact_matches) == 1:
        return exact_matches[0]

    if exact_matches:
        return None

    # Match the complete final segment, not a substring.
    # "808" matches "GRZ-TH-808", but not "GRZ-TH-1808".
    suffix_matches = [
        unit_name
        for unit_name in previous_units
        if str(unit_name).strip().casefold().rsplit("-", 1)[-1]
        == requested
    ]

    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None
