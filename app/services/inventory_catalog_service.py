
from dataclasses import dataclass

from app.schemas.retrieval import InventorySnapshot


@dataclass
class InventoryCatalogs:
    active_projects: list[str]
    unit_projects: list[str]


class InventoryCatalogService:

    @staticmethod
    def build(
        snapshot: InventorySnapshot,
    ) -> InventoryCatalogs:

        active_projects = sorted({
            project.project_name.strip()
            for project in snapshot.projects
            if project.project_name.strip()
        })

        unit_projects = sorted({
            unit.project_name.strip()
            for unit in snapshot.units
            if unit.project_name.strip()
        })

        return InventoryCatalogs(
            active_projects=active_projects,
            unit_projects=unit_projects,
        )
