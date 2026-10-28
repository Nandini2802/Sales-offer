
import pytest
from types import SimpleNamespace

from app.schemas.retrieval import (
    InventoryProject,
    InventoryUnit,
    InventorySnapshot,
)
from app.services.availability_resolver import (
    resolve_availability_project,
    AvailabilityResolutionError,
)
from app.services.availability_service import (
    extract_currency_codes,
)


@pytest.fixture
def snapshot():
    return InventorySnapshot(
        projects=[
            InventoryProject(
                project_id="PROJECT123",
                project_name="GREENZ BY DANUBE",
                project_number="1001",
            )
        ],
        units=[
            InventoryUnit(
                unit_id="UNIT123",
                unit_name="GRZ-TH-808",
                unit_code="808",
                project_id="PROJECT123",
                project_name="GREENZ BY DANUBE",
            )
        ],
    )


def make_intent(**kwargs):
    values = {
        "project_id": None,
        "project_number": None,
        "project_name": None,
        "unit_id": None,
        "unit_name": None,
        "unit_number": None,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "identifier",
    [
        {"project_id": "PROJECT123"},
        {"project_number": "1001"},
        {"project_name": "GREENZ BY DANUBE"},
        {"unit_id": "UNIT123"},
        {"unit_name": "GRZ-TH-808"},
        {"unit_number": "808"},
    ],
)
def test_project_resolution(snapshot, identifier):
    project = resolve_availability_project(
        make_intent(**identifier),
        snapshot,
    )
    assert project.project_id == "PROJECT123"


def test_missing_identifier(snapshot):
    with pytest.raises(AvailabilityResolutionError):
        resolve_availability_project(
            make_intent(),
            snapshot,
        )


def test_unknown_project(snapshot):
    with pytest.raises(AvailabilityResolutionError):
        resolve_availability_project(
            make_intent(project_id="INVALID"),
            snapshot,
        )


def test_currency_list():
    assert extract_currency_codes(
        '["AED", "USD", "INR"]'
    ) == {"AED", "USD", "INR"}


def test_currency_dictionary():
    assert extract_currency_codes(
        '{"AED": 1, "USD": 0.27}'
    ) == {"AED", "USD"}
