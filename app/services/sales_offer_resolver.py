
import re
from dataclasses import dataclass
from typing import Literal

from app.schemas.retrieval import InventorySnapshot
from app.services.project_name_service import normalize_project_name


class SalesOfferResolutionError(Exception):
    pass


@dataclass
class SalesOfferResolution:
    status: Literal["resolved", "confirm", "project_units"]
    unit: object | None = None
    units: list | None = None


def normalize_unit(value):
    """Ignore separators and case when comparing unit names."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def resolve_sales_offer_request(
    intent,
    snapshot: InventorySnapshot,
) -> SalesOfferResolution:

    requested_unit = (
        intent.unit_id or intent.unit_name or intent.unit_number
    )
    requested_project = intent.project_name
    requested_project_id = intent.project_id
    requested_project_number = intent.project_number

    units = list(snapshot.units)

    # Restrict candidates to the requested project.
    if requested_project_id:
        units = [
            u for u in units
            if str(u.project_id or "").casefold()
            == str(requested_project_id).casefold()
        ]

    if requested_project_number:
        project_ids = {
            p.project_id for p in snapshot.projects
            if str(p.project_number or "").strip()
            == str(requested_project_number).strip()
        }
        units = [u for u in units if u.project_id in project_ids]

    if requested_project:
        expected = normalize_project_name(requested_project)
        units = [
            u for u in units
            if normalize_project_name(u.project_name or "")
            == expected
        ]

    if requested_unit:
        requested = str(requested_unit).strip().casefold()

        # Exact ID, name, or code match first.
        exact = [
            u for u in units
            if requested in {
                str(u.unit_id or "").strip().casefold(),
                str(u.unit_name or "").strip().casefold(),
                str(u.unit_code or "").strip().casefold(),
            }
        ]

        exact = {u.unit_id: u for u in exact if u.unit_id}

        if len(exact) == 1:
            return SalesOfferResolution(
                status="resolved",
                unit=next(iter(exact.values())),
            )

        if len(exact) > 1:
            raise SalesOfferResolutionError(
                "Multiple units match your request. "
                "Please provide the complete Unit ID."
            )

        # Only fuzzy-normalize unit names/codes, never Salesforce IDs.
        normalized = normalize_unit(requested_unit)
        candidates = {
            u.unit_id: u for u in units
            if u.unit_id and (
                normalize_unit(u.unit_name) == normalized
                or normalize_unit(u.unit_code) == normalized
            )
        }

        if len(candidates) == 1:
            return SalesOfferResolution(
                status="confirm",
                unit=next(iter(candidates.values())),
            )

        if len(candidates) > 1:
            raise SalesOfferResolutionError(
                "Multiple units match your request. "
                "Please provide the complete Unit ID."
            )

        raise SalesOfferResolutionError(
            "Please specify the unit for which "
            "you want to generate the sales offer."
        )

    # Project-only request.
    if (
        requested_project
        or requested_project_id
        or requested_project_number
    ):
        unique = {u.unit_id: u for u in units if u.unit_id}

        if unique:
            return SalesOfferResolution(
                status="project_units",
                units=list(unique.values()),
            )

    raise SalesOfferResolutionError(
        "Please specify the unit for which "
        "you want to generate the sales offer."
    )


def resolve_sales_offer_unit(intent, snapshot):
    """Compatibility wrapper for existing callers."""
    result = resolve_sales_offer_request(intent, snapshot)

    if result.status != "resolved":
        raise SalesOfferResolutionError(
            "Please specify the unit for which "
            "you want to generate the sales offer."
        )

    return result.unit
