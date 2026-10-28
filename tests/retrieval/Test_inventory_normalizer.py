
from app.retrieval.inventory_normalizer import (
    normalize_project,
    normalize_unit,
)


def test_project_preserves_api_fields():
    raw = {
        "Id": "project-123",
        "ProjectName": "GREENZ BY DANUBE",
        "Total_Units__c": 0,
        "Service_Charge__c": None,
        "EOIActive ": False,
        "Payment_Plan_Mob__c ": None,
        "Custom_Future_Field__c": "New value",
    }

    project = normalize_project(raw)

    assert project.project_name == "GREENZ BY DANUBE"
    assert project.total_units == 0
    assert project.service_charge is None
    assert project.eoi_active is False
    assert project.payment_plan is None
    assert project.attributes == raw
    assert (
        project.attributes["Custom_Future_Field__c"]
        == "New value"
    )


def test_unit_preserves_api_fields():
    raw = {
        "unitId": "unit-123",
        "Name": "ASPZ-F02-11013",
        "projectName": "ASPIRZ BY DANUBE",
        "NumberOfBedrooms": None,
        "Unit Type": "1 Bedroom",
        "SellingPrice__c": 2770002,
        "currency_symbol": "AED",
        "is_show_villa": False,
    }

    unit = normalize_unit(raw)

    assert unit.bedrooms is None
    assert unit.unit_type == "1 Bedroom"
    assert unit.price == 2770002
    assert unit.currency == "AED"
    assert unit.is_show_villa is False
    assert unit.attributes == raw
