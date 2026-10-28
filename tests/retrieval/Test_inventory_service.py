
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.retrieval import InventoryUnit
from app.services.inventory_filter_service import InventoryFilterService

filter_service = InventoryFilterService()


def sample_units():
    return [
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
        InventoryUnit(
            unit_id="3",
            unit_name="A-103",
            project_name="Test Project",
            bedrooms=3,
            price=2500000,
            area_sqft=1600,
            currency="AED",
            status="Booked",
        ),
    ]


def make_intent(**overrides):
    values = {
        "project_name": "Test Project",
        "unit_number": None,
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


def test_filter_by_bedrooms():
    result = filter_service.filter_units(
        sample_units(),
        make_intent(bedrooms=2),
    )
    assert [u.unit_name for u in result] == ["A-102"]


def test_filter_by_max_price():
    result = filter_service.filter_units(
        sample_units(),
        make_intent(max_price=Decimal("1600000")),
    )
    assert {u.unit_name for u in result} == {"A-101", "A-102"}


def test_combined_filters():
    result = filter_service.filter_units(
        sample_units(),
        make_intent(
            bedrooms=2,
            max_price=Decimal("2000000"),
            status="Available",
        ),
    )
    assert [u.unit_name for u in result] == ["A-102"]


def test_no_matching_units():
    result = filter_service.filter_units(
        sample_units(),
        make_intent(bedrooms=4),
    )
    assert result == []


def test_price_sort_ascending():
    result = filter_service.filter_units(
        sample_units(),
        make_intent(sort_by="price_asc"),
    )
    assert [u.unit_name for u in result] == [
        "A-101", "A-102", "A-103"
    ]
