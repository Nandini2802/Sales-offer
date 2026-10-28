
import pytest
from types import SimpleNamespace

from app.schemas.retrieval import (
    InventoryProject,
    InventoryUnit,
    InventorySnapshot,
)
from app.handlers.inventory_handler import InventoryHandler


@pytest.fixture
def snapshot():
    return InventorySnapshot(
        projects=[
            InventoryProject(
                project_id="P1",
                project_name="Test Project",
                location="Dubai",
            )
        ],
        units=[
            InventoryUnit(
                unit_id="1",
                unit_name="A-101",
                project_name="Test Project",
                bedrooms=1,
                price=900000,
                area_sqft=650,
                currency="AED",
                status="Available",
            ),
            InventoryUnit(
                unit_id="2",
                unit_name="A-102",
                project_name="Test Project",
                bedrooms=2,
                price=1500000,
                area_sqft=1100,
                currency="AED",
                status="Available",
            ),
        ],
    )


def make_intent(**overrides):
    values = {
        "intent": "inventory",
        "inventory_scope": "units",
        "inventory_operation": "unit_search",
        "project_name": "Test Project",
        "unit_number": None,
        "compare_unit_numbers": [],
        "bedrooms": None,
        "unit_type": None,
        "category": None,
        "status": None,
        "floor_number": None,
        "min_price": None,
        "max_price": None,
        "min_area_sqft": None,
        "max_area_sqft": None,
        "sort_by": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_search_units(snapshot):
    handler = InventoryHandler(snapshot)
    result = await handler.handle(
        make_intent(bedrooms=2)
    )

    assert result.intent == "inventory"
    assert result.has_data is True
    assert len(result.html_blocks) > 0


@pytest.mark.asyncio
async def test_no_matching_units(snapshot):
    handler = InventoryHandler(snapshot)
    result = await handler.handle(
        make_intent(bedrooms=5)
    )

    assert result.has_data is False
    assert len(result.messages) > 0


@pytest.mark.asyncio
async def test_project_information(snapshot):
    handler = InventoryHandler(snapshot)
    result = await handler.handle(
        make_intent(
            inventory_scope="projects",
            inventory_operation="project_info",
        )
    )

    assert result.has_data is True
    assert result.generation_context


@pytest.mark.asyncio
async def test_compare_two_units(snapshot):
    handler = InventoryHandler(snapshot)
    result = await handler.handle(
        make_intent(
            inventory_operation="unit_comparison",
            compare_unit_numbers=["A-101", "A-102"],
        )
    )

    assert result.has_data is True
    assert result.generation_context
