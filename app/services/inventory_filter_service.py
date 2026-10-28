from decimal import Decimal, InvalidOperation
import re

from app.schemas.retrieval import InventoryUnit
from app.schemas.routing import RoutingIntent


def norm(value) -> str:
    return str(value or "").strip().casefold()


def as_decimal(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        cleaned = str(value).replace(",", "").strip()

        if not cleaned:
            return None

        number = Decimal(cleaned)
        return number if number.is_finite() else None

    except (InvalidOperation, ValueError):
        return None


def as_bedrooms(value) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    text = norm(value)

    if text in {"studio", "st", "0", "0.0"}:
        return 0

    match = re.fullmatch(
        r"(\d+)(?:\.0+)?(?:\s*(?:br|bed|bedroom|bedrooms))?",
        text,
    )

    if match:
        return int(match.group(1))

    return None


class InventoryFilterService:

    def filter_units(
        self,
        units: list[InventoryUnit],
        intent: RoutingIntent,
    ) -> list[InventoryUnit]:

        results = []

        for unit in units:

            # 1. Match official project name
            if intent.project_name:
                if norm(unit.project_name) != norm(
                    intent.project_name
                ):
                    continue

            # 2. Unit identifier
            if intent.unit_number:
                requested = norm(intent.unit_number)

                identifiers = {
                    norm(unit.unit_name),
                    norm(unit.unit_code),
                }

                if requested not in identifiers:
                    continue

            # 3. Bedrooms
            if intent.bedrooms is not None:
                bedrooms = as_bedrooms(unit.bedrooms)

                if bedrooms != intent.bedrooms:
                    continue

            # 4. Unit classification
            if intent.unit_type:
                if norm(unit.unit_type) != norm(
                    intent.unit_type
                ):
                    continue

            if intent.category:
                if norm(unit.category) != norm(
                    intent.category
                ):
                    continue

            # 5. Status
            if intent.status:
                if norm(unit.status) != norm(
                    intent.status
                ):
                    continue

            # 6. Floor
            if intent.floor_number:
                if norm(unit.floor_number) != norm(
                    intent.floor_number
                ):
                    continue

            # 7. Price
            price = as_decimal(unit.price)

            if intent.min_price is not None:
                if price is None or price < intent.min_price:
                    continue

            if intent.max_price is not None:
                if price is None or price > intent.max_price:
                    continue

            # 8. Area
            area = as_decimal(unit.area_sqft)

            if intent.min_area_sqft is not None:
                if area is None or area < intent.min_area_sqft:
                    continue

            if intent.max_area_sqft is not None:
                if area is None or area > intent.max_area_sqft:
                    continue

            results.append(unit)

        # 9. Sorting
        if intent.sort_by:

            sort_fields = {
                "price_asc": ("price", False),
                "price_desc": ("price", True),
                "area_asc": ("area_sqft", False),
                "area_desc": ("area_sqft", True),
            }

            field, reverse = sort_fields[intent.sort_by]

            known = [
                unit for unit in results
                if as_decimal(getattr(unit, field)) is not None
            ]

            unknown = [
                unit for unit in results
                if as_decimal(getattr(unit, field)) is None
            ]

            known.sort(
                key=lambda unit: as_decimal(
                    getattr(unit, field)
                ),
                reverse=reverse,
            )

            results = known + unknown

        return results