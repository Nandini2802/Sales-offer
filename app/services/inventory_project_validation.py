from dataclasses import dataclass
from app.schemas.retrieval import InventorySnapshot


@dataclass
class ProjectValidation:
    valid: bool
    project_name: str | None
    reason: str | None = None


def validate_inventory_project(
    project_name: str | None,
    snapshot: InventorySnapshot,
    scope: str = "units",
) -> ProjectValidation:
    """
    Validate an LLM-selected project against the
    appropriate live Inventory API catalog.

    No regex, fuzzy matching, or name correction.
    """

    if project_name is None:
        return ProjectValidation(
            valid=True,
            project_name=None,
        )

    if scope == "units":
        valid_names = {
            unit.project_name
            for unit in snapshot.units
        }
    elif scope == "projects":
        valid_names = {
            project.project_name
            for project in snapshot.projects
        }
    else:
        raise ValueError(
            "scope must be 'units' or 'projects'"
        )

    if project_name in valid_names:
        return ProjectValidation(
            valid=True,
            project_name=project_name,
        )

    return ProjectValidation(
        valid=False,
        project_name=None,
        reason="PROJECT_NOT_IN_SELECTED_CATALOG",
    )
