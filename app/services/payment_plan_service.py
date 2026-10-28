from app.services.project_name_service import (
    normalize_project_name,
)


def resolve_payment_plan_units(
    snapshot,
    *,
    project_name=None,
    project_number=None,
    unit_number=None,
):
    if unit_number:
        requested = unit_number.strip().casefold()

        return [
            unit
            for unit in snapshot.units
            if requested in {
                str(unit.unit_id or "").casefold(),
                str(unit.unit_name or "").casefold(),
                str(unit.unit_code or "").casefold(),
            }
            and (
                not project_name
                or normalize_project_name(unit.project_name)
                == normalize_project_name(project_name)
            )
        ]

    projects = snapshot.projects

    if project_number:
        projects = [
            project
            for project in projects
            if str(project.project_number or "").strip()
            == str(project_number).strip()
        ]

    if project_name:
        projects = [
            project
            for project in projects
            if normalize_project_name(project.project_name)
            == normalize_project_name(project_name)
        ]

    if not project_name and not project_number:
        return []

    project_ids = {
        project.project_id
        for project in projects
        if project.project_id
    }

    project_names = {
        normalize_project_name(project.project_name)
        for project in projects
        if project.project_name
    }

    return [
        unit
        for unit in snapshot.units
        if (
            unit.project_id in project_ids
            or normalize_project_name(unit.project_name)
            in project_names
        )
    ]