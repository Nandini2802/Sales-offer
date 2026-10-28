from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class InventoryBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )

class InventoryProjectFile(InventoryBaseModel):

    file_url: str | None = Field(
        default=None,
        alias="fileUrl",
    )

    file_type: str | None = Field(
        default=None,
        alias="fileType",
    )

    file_name: str | None = Field(
        default=None,
        alias="fileName",
    )

class InventoryProject(InventoryBaseModel):

    project_id: str | None = None
    project_name: str | None = None
    project_number: str | None = None
    project_web_id: str | None = None
    project_sequence: str | None = None

    files: list[InventoryProjectFile] = Field(
        default_factory=list
    )

    enable_project_for: Any = None
    enable_brandmorph_pitch: bool | None = None
    enable_brandmorph_presentation: bool | None = None
    project_configuration: Any = None
    eoi_active: bool | None = None
    service_charge: str | None = None
    construction_status: str | None = None
    handover_date: str | None = None
    completion_date: str | None = None
    location: str | None = None
    bedrooms_categories: str | None = None
    apartments: str | None = None
    payment_plan: str | None = None
    starting_price: str | None = None
    project_image: str | None = None
    unit_of_measurement: str | None = None
    total_units: int | None = None
    total_sold_units: int | None = None
    total_selling_price: float | None = None
    total_saleable_area: float | None = None
    total_residential_units: int | None = None
    total_other_units: int | None = None
    total_new_units: int | None = None
    total_floors: int | None = None
    total_commercial_units: int | None = None
    total_buildings: int | None = None
    total_booked_units: int | None = None
    total_bua_sqft: float | None = None
    total_available_units: int | None = None
    total_available_residential_units: int | None = None
    total_available_commercial_units: int | None = None
    plot_size_sqft: float | None = None

    places_nearby: Any = None
    building_type: str | None = None
    amenities: Any = None

    attributes: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
    )

class InventoryUnit(InventoryBaseModel):

    unit_id: str | None = None
    unit_name: str | None = None
    unit_code: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    project_code: str | None = None

    project_location: str | None = None
    building_id: str | None = None
    building_name: str | None = None
    building_code: str | None = None

    floor_number: str | None = None
    floor_code: str | None = None
    category: str | None = None
    typology: str | None = None
    unit_type: str | None = None

    bedrooms: int | None = None
    bathrooms: int | None = None
    parking_spaces: int | None = None
    internal_saleable_area: float | None = None

    area_sqft: float | None = None

    plot_area: float | None = None
    view: str | None = None
    price: float | None = None
    currency: str | None = None
    status: str | None = None
    handover_status: str | None = None
    construction_status: str | None = None

    is_show_villa: bool | None = None

    attributes: dict[str, Any] = Field(
        default_factory=dict,
        exclude=True,
    )

class InventorySnapshot(BaseModel):

    projects: list[InventoryProject] = Field(
        default_factory=list
    )

    units: list[InventoryUnit] = Field(
        default_factory=list
    )
