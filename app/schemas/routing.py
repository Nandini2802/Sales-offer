from typing import Literal
from pydantic import BaseModel, Field
from decimal import Decimal


IntentType = Literal[
    "greeting",
    "marketing",
    "inventory",
    "excel_walkthrough",
    "download_availability",
    "sales_offer",
    "bank_details",
    "project_information",
    "out_of_scope",
]


class RoutingIntent(BaseModel):
    intent: IntentType

    feature_name: str | None = None

    # Original part of the user query
    original_query: str

    # Search-ready version of the request
    expanded_query: str

    # Requested operation
    action: str

    # Extracted entities
    project_name: str | None
    unit_number: str | None

    # Additional filters/parameters
    bedrooms: int | None
    currency: str | None
    file_format: str | None
    bank_account_types: list[str]
    marketing_assets: list[str]

    # Clarification
    missing_fields: list[str]
    requires_clarification: bool

    # Inventory
    inventory_scope: Literal["units", "projects"] | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_area_sqft: float | None = None
    max_area_sqft: float | None = None

    unit_type: str | None = None
    category: str | None = None
    status: str | None = None
    floor_number: str | None = None

    project_number: str | None = None
    project_id: str | None = None
    unit_id: str | None = None
    unit_name: str | None = None

    bank_id: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_account_index: int | None = None

    payment_plan_ids: list[str] = Field(default_factory=list)
    payment_plan_numbers: list[int] = Field(default_factory=list)
    offer_id: str | None = None
    project_limit: int | None = None

    project_location: str | None = None

    sort_by: Literal[
        "price_asc",
        "price_desc",
        "area_asc",
        "area_desc",
    ] | None = None

    inventory_operation: Literal[
        "project_info",
        "project_comparison",
        "unit_search",
        "unit_details",
        "unit_comparison",
        "payment_plan",
    ] | None = None

    project_operation: Literal[
        "latest",
        "list",
        "details",
        "location_search",
        "tour",
    ] | None = None

    compare_unit_numbers: list[str] = Field(
        default_factory=list,
    )

    compare_project_names: list[str] = Field(
        default_factory=list,
    )

    


class RoutingResult(BaseModel):
    language: str
    intents: list[RoutingIntent] = Field(min_length=1)
    requires_clarification: bool