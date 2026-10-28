
from app.services.unit_comparison_mapper import (
    map_comparison,
    first_available,
)

project = {
    "Name": "GREENZ BY DANUBE",
    "Location_Name_Mob__c": "Academic City, Dubai",
    "Payment_Plans__r": {
        "records": [
            {
                "Name": "Standard Payment Plan",
                "Number_of_Installments__c": 4,
            }
        ]
    },
}

unit = {
    "Name": "GRZ-TH-808",
    "CurrencyIsoCode": "AED",
    "SellingPrice__c": "1,296,000.00",
    "Category__c": "Residential",
    "Unit_Type1__c": "4 BHK Premium",
    "Unit_Type2__c": None,
    "NumberOfBathrooms__c": None,
    "NumberOfCarParks__c": None,
    "Total_Saleable_Area_In_Sq_Ft__c": 3100,
    "Unit_Size__c": None,
    "Internal_Saleable_Area__c": 2000,
    "PlotArea__c": 1453.13,
    "Is_Handovered__c": False,
    "Status__c": "Available",
}

result = map_comparison(project, unit)
mapped = result["unit"]

assert mapped["unit_name"] == "GRZ-TH-808"
assert mapped["unit_type"] == "Residential"
assert mapped["parking"] == "--"
assert mapped["total_area"] == "3,100 SQFT"
assert mapped["internal_area"] == "2,000 SQFT"
assert mapped["status"] == "Not Handed Over"
assert mapped["completion_date"] == "Available"

# Test all three Unit Type fallback cases.
assert first_available(
    {"Category__c": None, "Unit_Type1__c": "Studio"},
    "Category__c", "Unit_Type1__c", "Unit_Type2__c"
) == "Studio"

assert first_available(
    {
        "Category__c": None,
        "Unit_Type1__c": None,
        "Unit_Type2__c": "Apartment",
    },
    "Category__c", "Unit_Type1__c", "Unit_Type2__c"
) == "Apartment"

assert first_available(
    {},
    "Category__c", "Unit_Type1__c", "Unit_Type2__c"
) is None

print("All unit comparison mapping tests passed.")
print(mapped)
