
"""
Google Maps utility for Danube Chatbot.

Responsibilities:
- Validate latitude and longitude.
- Use Google Geocoding API with the provided API key.
- Generate Google Maps URLs using coordinates.
- Return the generated URL to the project information handler.

Google Maps data source:
    Project Coordinates API -> Latitude/Longitude

Note:
    OSF Portfolio is NOT used for Google Maps.
    It remains available separately for 3D tours.

Security:
    The Google Maps API key must be supplied by the caller
    through the existing secrets-management system:
    - Local: LocalSecrets / .env
    - Azure: Azure Key Vault

    The API key is never included in the returned Maps URL.
"""

import re
import math
import logging

from urllib.parse import urlencode

import httpx


logger = logging.getLogger(__name__)


def normalize_map_project_name(
    value: str | None,
) -> str:

    if not value:
        return ""

    name = str(value).strip().casefold()

    name = re.sub(
        r"\bby\s+danube(?:\s+properties)?\b",
        "",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    return name.strip()


def validate_coordinates(
    latitude,
    longitude,
) -> tuple[float, float]:

    if latitude is None or longitude is None:
        raise ValueError(
            "Latitude and longitude are required"
        )

    try:
        latitude = float(latitude)
        longitude = float(longitude)

    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Latitude and longitude must be numeric"
        ) from exc

    # Reject NaN and infinity.
    if not (
        math.isfinite(latitude)
        and math.isfinite(longitude)
    ):
        raise ValueError(
            "Latitude and longitude must be finite"
        )

    if not (-90 <= latitude <= 90):
        raise ValueError(
            f"Invalid latitude: {latitude}"
        )

    if not (-180 <= longitude <= 180):
        raise ValueError(
            f"Invalid longitude: {longitude}"
        )

    return latitude, longitude


def build_google_maps_url_from_coordinates(
    latitude: float,
    longitude: float,
) -> str:

    latitude, longitude = validate_coordinates(
        latitude,
        longitude,
    )

    query = urlencode({
        "api": 1,
        "query": f"{latitude},{longitude}",
    })

    return (
        "https://www.google.com/maps/search/?"
        + query
    )


async def generate_map_url_from_coordinates(
    latitude: float,
    longitude: float,
    google_api_key: str,
) -> str:

    """
    Validate coordinates using Google's Geocoding API
    and generate a Google Maps link.

    Steps:
    1. Validate latitude and longitude.
    2. Validate the supplied Google API key.
    3. Call Google Geocoding API.
    4. Check Google API response.
    5. Generate Google Maps URL using original
       latitude and longitude.
    6. Return the URL.

    The API key must be retrieved by the caller
    using the application's existing secrets service.

    The API key is never included in the returned URL.
    """

    # Step 1: Validate coordinates.

    latitude, longitude = validate_coordinates(
        latitude,
        longitude,
    )

    # Step 2: Validate supplied Google Maps API key.

    if (
        not isinstance(google_api_key, str)
        or not google_api_key.strip()
    ):
        raise ValueError(
            "Google Maps API key is missing"
        )

    google_api_key = google_api_key.strip()

    # Step 3: Call Google Geocoding API.

    google_api_url = (
        "https://maps.googleapis.com"
        "/maps/api/geocode/json"
    )

    params = {
        "latlng": f"{latitude},{longitude}",
        "key": google_api_key,
    }

    try:

        async with httpx.AsyncClient(
            timeout=15.0
        ) as client:

            response = await client.get(
                google_api_url,
                params=params,
            )

            response.raise_for_status()

            result = response.json()

    except httpx.HTTPStatusError as exc:

        logger.error(
            "GOOGLE_MAPS_HTTP_ERROR | "
            "status_code=%s",
            exc.response.status_code,
        )

        raise RuntimeError(
            "Google Maps API HTTP request failed"
        ) from exc

    except httpx.RequestError as exc:

        logger.error(
            "GOOGLE_MAPS_CONNECTION_ERROR | "
            "error_type=%s",
            type(exc).__name__,
        )

        raise RuntimeError(
            "Unable to connect to Google Maps API"
        ) from exc

    # Step 4: Validate Google API response.

    api_status = result.get("status")

    if api_status != "OK":

        logger.error(
            "GOOGLE_MAPS_API_FAILED | "
            "status=%s",
            api_status,
        )

        raise RuntimeError(
            "Google Maps Geocoding API failed: "
            f"{api_status}"
        )

    # Step 5: Generate Google Maps URL.

    map_url = (
        build_google_maps_url_from_coordinates(
            latitude=latitude,
            longitude=longitude,
        )
    )

    logger.info(
        "GOOGLE_MAPS_URL_GENERATED"
    )

    # Step 6: Return URL.

    return map_url
