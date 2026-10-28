from app.schemas.retrieval import InventoryUnit
from app.schemas.routing import RoutingIntent
from app.services.inventory_filter_service import (
    InventoryFilterService,
)


def make_intent(**overrides):
    payload = {
        "intent": "inventory",
        "original_query": "Show me units",
        "expanded_query": "Show me units",
        "action": "search",
        "project_name": None,
        "unit_number": None,
        "bedrooms": None,
        "currency": None,
        "file_format": None,
        "bank_account_types": [],
        "marketing_assets": [],
        "missing_fields": [],
        "requires_clarification": False,
        "inventory_scope": "units",
        "inventory_operation": "unit_search",
    }

    payload.update(overrides)

    return RoutingIntent(**payload)


def test_project_bedrooms_price_and_sort():

    units = [
        InventoryUnit(
            unit_name="G-101",
            project_name="GREENZ BY DANUBE",
            bedrooms="2",
            price="1800000",
        ),
        InventoryUnit(
            unit_name="G-102",
            project_name="GREENZ BY DANUBE",
            bedrooms="2",
            price="1500000",
        ),
        InventoryUnit(
            unit_name="G-103",
            project_name="GREENZ BY DANUBE",
            bedrooms="3",
            price="1700000",
        ),
    ]

    intent = make_intent(
        project_name="GREENZ BY DANUBE",
        bedrooms=2,
        max_price=2000000,
        sort_by="price_asc",
    )

    result = InventoryFilterService().filter_units(
        units,
        intent,
    )

    assert [unit.unit_name for unit in result] == [
        "G-102",
        "G-101",
    ]