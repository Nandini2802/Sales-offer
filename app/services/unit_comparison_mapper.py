
from datetime import date
from decimal import Decimal, InvalidOperation


def display(value):
    if value is None:
        return "--"

    if isinstance(value, str):
        value = value.strip()
        return value if value else "--"

    return str(value)


def first_available(data, *fields):
    """
    Return the first non-null, non-empty field.
    Return None when all fields are missing.
    """
    for field in fields:
        value = data.get(field)

        if value is not None and (
            not isinstance(value, str)
            or value.strip()
        ):
            return value

    return None


def format_price(value):
    if value is None or str(value).strip() == "":
        return "--"

    try:
        amount = Decimal(str(value).replace(",", ""))
        if not amount.is_finite():
            return "--"
        return f"{amount:,.2f}"
    except (InvalidOperation, ValueError):
        return "--"


def format_area(value):
    if value is None or str(value).strip() == "":
        return "--"

    try:
        amount = Decimal(str(value).replace(",", ""))
        if not amount.is_finite():
            return "--"
        number = f"{amount:,.2f}".rstrip("0").rstrip(".")
        return f"{number} SQFT"
    except (InvalidOperation, ValueError):
        return "--"


def format_date(value):
    if not value:
        return "--"

    try:
        parsed = date.fromisoformat(str(value)[:10])
        return parsed.strftime("%B %Y")
    except (ValueError, TypeError):
        return "--"


def format_handover_status(value):
    """
    Is_Handovered__c is a boolean field.
    """
    if value is True:
        return "Handed Over"

    if value is False:
        return "Not Handed Over"

    return "--"


def map_comparison(project, unit):
    raw_plans = (
        (project.get("Payment_Plans__r") or {})
        .get("records") or []
    )

    payment_plans = []

    for plan in raw_plans:
        if not isinstance(plan, dict):
            continue

        payment_plans.append({
            "name": display(plan.get("Name")),
            "installment_count": display(
                plan.get("Number_of_Installments__c")
            ),
        })

    return {
        "unit": {
            "unit_name": display(unit.get("Name")),
            "currency": display(unit.get("CurrencyIsoCode")),
            "price": format_price(unit.get("SellingPrice__c")),

            "project_name": display(project.get("Name")),
            "project_location": display(
                project.get("Location_Name_Mob__c")
            ),

            "category": display(unit.get("Category__c")),

            # Priority: Category -> Unit Type 1 -> Unit Type 2
            "unit_type": display(
                first_available(
                    unit,
                    "Category__c",
                    "Unit_Type1__c",
                    "Unit_Type2__c",
                )
            ),

            "bathrooms": display(
                unit.get("NumberOfBathrooms__c")
            ),

            "parking": display(
                unit.get("NumberOfCarParks__c")
            ),

            # Priority: Total Saleable Area -> Unit Size
            "total_area": format_area(
                first_available(
                    unit,
                    "Total_Saleable_Area_In_Sq_Ft__c",
                    "Unit_Size__c",
                )
            ),

            "internal_area": format_area(
                unit.get("Internal_Saleable_Area__c")
            ),

            "plot_area": format_area(
                unit.get("PlotArea__c")
            ),

            "status": format_handover_status(
                unit.get("Is_Handovered__c")
            ),

            # Status__c is a text field, not a date.
            "completion_date": display(
                unit.get("Status__c")
            ),
        },
        "payment_plans": payment_plans,
    }
