import re
from dataclasses import dataclass

from app.schemas.retrieval import InventorySnapshot
from app.services.project_resolution_service import (
    match_project_reference,
)


class AvailabilityResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedAvailabilityProject:
    project_id: str
    project_name: str


def normalize(value: str | None) -> str:
    text = str(value or "").casefold().strip()
    text = re.sub(r"\bby\s+danube\b", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def resolve_availability_project(
    intent,
    snapshot: InventorySnapshot,
) -> ResolvedAvailabilityProject:

    projects = {}

    # Active projects
    for project in snapshot.projects:
        if project.project_id:
            projects[str(project.project_id)] = {
                "id": str(project.project_id),
                "name": project.project_name or "",
                "number": project.project_number,
            }

    units = snapshot.units

    identifiers = {
        "project_id": intent.project_id,
        "project_number": intent.project_number,
        "project_name": intent.project_name,
        "unit_id": intent.unit_id,
        "unit_name": intent.unit_name,
        "unit_number": intent.unit_number,
    }

    supplied = {
        key: value
        for key, value in identifiers.items()
        if value is not None and str(value).strip()
    }

    if not supplied:
        raise AvailabilityResolutionError(
            "Please specify a project name, project number, "
            "project ID, or unit identifier."
        )

    candidate_sets = []

    if intent.project_id:
        candidate_sets.append({
            pid for pid in projects
            if normalize(pid) == normalize(intent.project_id)
        })

    if intent.project_number:
        candidate_sets.append({
            pid for pid, project in projects.items()
            if normalize(project["number"])
            == normalize(intent.project_number)
        })

    if intent.project_name:

        # Build project name to ID mapping
        project_names = {
            project["name"]: pid
            for pid, project in projects.items()
            if project["name"]
        }

        # Reuse existing Bank Details project matching
        resolution = match_project_reference(
            intent.project_name,
            project_names.keys(),
        )

        if resolution.status == "matched":

            candidate_sets.append({
                pid
                for pid, project in projects.items()
                if project["name"] == resolution.name
            })

        elif resolution.status == "ambiguous":

            raise AvailabilityResolutionError(
                "Multiple projects match your request: "
                + ", ".join(resolution.candidates[:5])
                + ". Please specify the correct project."
            )

        else:

            candidate_sets.append(set())

    for field, attributes in (
        ("unit_id", ("unit_id",)),
        ("unit_name", ("unit_name",)),
        ("unit_number", ("unit_name", "unit_code")),
    ):
        value = getattr(intent, field, None)
        if not value:
            continue

        matched = set()

        for unit in units:
            if any(
                normalize(getattr(unit, attr, None))
                == normalize(value)
                for attr in attributes
            ):
                if unit.project_id:
                    matched.add(str(unit.project_id))

        candidate_sets.append(matched)

    if not candidate_sets:
        raise AvailabilityResolutionError(
            "Please specify a project or unit."
        )

    matching_ids = set.intersection(*candidate_sets)

    if not matching_ids:
        raise AvailabilityResolutionError(
            "I couldn't find a matching authorized project. "
            "Please check the project or unit details."
        )

    if len(matching_ids) > 1:
        names = [
            projects[pid]["name"]
            for pid in sorted(matching_ids)
            if pid in projects
        ]
        raise AvailabilityResolutionError(
            "Multiple projects match your request: "
            + ", ".join(names[:5])
            + ". Please specify the correct project."
        )

    project_id = next(iter(matching_ids))

    if project_id not in projects:
        raise AvailabilityResolutionError(
            "The selected project is not available "
            "in the authorized project catalog."
        )

    project = projects[project_id]

    return ResolvedAvailabilityProject(
        project_id=project_id,
        project_name=project["name"],
    )
