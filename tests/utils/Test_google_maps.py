
import asyncio
import os
import sys

from pathlib import Path

from dotenv import load_dotenv


# Allow running this file directly from the project root.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


from app.retrieval.project_coordinates_connector import (
    ProjectCoordinatesConnector,
)
from app.core.keyvault import load_application_secrets
from app.utils.google_maps import (
    generate_map_url_from_coordinates,
)
from app.services.template_service import TemplateService


async def main():

    project_id = os.getenv(
        "TEST_PROJECT_ID",
        "a14NM000000x22zYAA",
    )

    access_token = os.getenv(
        "TEST_SALESFORCE_ACCESS_TOKEN"
    )

    if not access_token:
        raise ValueError(
            "TEST_SALESFORCE_ACCESS_TOKEN is missing"
        )

    print("\nSTEP 1: Fetching project coordinates")

    connector = ProjectCoordinatesConnector()

    coordinates = await connector.fetch_coordinates(
        project_id=project_id,
        access_token=access_token,
    )

    print("Coordinates:", coordinates)

    if not coordinates:
        raise RuntimeError(
            "No coordinates returned by the API"
        )

    print("\nSTEP 2: Generating Google Maps URL")

    secrets = await load_application_secrets()

    map_url = await generate_map_url_from_coordinates(
        latitude=coordinates["latitude"],
        longitude=coordinates["longitude"],
        google_api_key=secrets.google_maps_api_key.get_secret_value(),
    )

    print("Google Maps URL:", map_url)

    print("\nSTEP 3: Rendering project HTML")

    templates = TemplateService()

    html = templates.render(
        "project_information_card.html.j2",
        project_name="ELITZ 3 BY DANUBE",
        image_url=None,
        starting_price=None,
        total_units=0,
        location="Dubai",
        map_url=map_url,
    )

    if "View Map" not in html:
        raise AssertionError(
            "View Map link is missing from HTML"
        )

    if map_url not in html:
        # Jinja autoescaping may encode & as &amp;.
        escaped_url = map_url.replace("&", "&amp;")

        if escaped_url not in html:
            raise AssertionError(
                "Generated map URL is missing from HTML"
            )

    output_file = ROOT / "tests" / "utils" / "project_map_test.html"

    output_file.write_text(
        html,
        encoding="utf-8",
    )

    print("HTML saved to:", output_file)
    print("\nSUCCESS: API, Google Maps, and HTML passed")


if __name__ == "__main__":
    asyncio.run(main())
