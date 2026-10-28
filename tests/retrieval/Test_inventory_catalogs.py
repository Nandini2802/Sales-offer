
from app.schemas.retrieval import (
    InventoryProject,
    InventoryUnit,
    InventorySnapshot,
)
from app.services.inventory_catalog_service import (
    InventoryCatalogService,
)
from app.services.inventory_project_validation import (
    validate_inventory_project,
)


def make_snapshot():
    return InventorySnapshot(
        projects=[
            InventoryProject(
                project_name="GREENZ BY DANUBE"
            ),
            InventoryProject(
                project_name="OCEANZ 1 BY DANUBE"
            ),
            InventoryProject(
                project_name="OCEANZ 2 BY DANUBE"
            ),
        ],
        units=[
            InventoryUnit(
                unit_name="G-101",
                project_name="GREENZ BY DANUBE",
            ),
            InventoryUnit(
                unit_name="G-102",
                project_name="GREENZ BY DANUBE",
            ),
        ],
    )


def test_separate_catalogs():
    catalogs = InventoryCatalogService.build(
        make_snapshot()
    )

    assert len(catalogs.active_projects) == 3
    assert catalogs.unit_projects == [
        "GREENZ BY DANUBE"
    ]


def test_project_is_active_but_has_no_visible_units():
    snapshot = make_snapshot()

    active_result = validate_inventory_project(
        "OCEANZ 1 BY DANUBE",
        snapshot,
        scope="projects",
    )

    units_result = validate_inventory_project(
        "OCEANZ 1 BY DANUBE",
        snapshot,
        scope="units",
    )

    assert active_result.valid is True
    assert units_result.valid is False


def test_valid_unit_project():
    result = validate_inventory_project(
        "GREENZ BY DANUBE",
        make_snapshot(),
        scope="units",
    )

    assert result.valid is True


def test_unknown_project():
    result = validate_inventory_project(
        "UNKNOWN PROJECT",
        make_snapshot(),
        scope="projects",
    )

    assert result.valid is False
