
import asyncio
import logging
import re

from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.core.keyvault import load_application_secrets
from app.schemas.handler_result import HandlerResult

from app.retrieval.project_information_connector import (
    ProjectInformationConnector,
    ProjectInformationAPIError,
)

from app.retrieval.project_coordinates_connector import (
    ProjectCoordinatesConnector,
)

from app.retrieval.osf_portfolio_connector import (
    OSFPortfolioConnector,
)

from app.services.template_service import TemplateService

from app.utils.google_maps import (
    normalize_map_project_name,
    generate_map_url_from_coordinates,
)

from app.utils.project_tours import (
    build_project_tour_lookup,
)


logger = logging.getLogger(__name__)


def normalize(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").casefold(),
    )


class ImageURLParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.urls = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a" and attrs.get("href"):
            self.urls.append(attrs["href"])

        if tag == "img" and attrs.get("src"):
            self.urls.append(attrs["src"])

    def handle_data(self, data):
        self.text.append(data)


def safe_image_url(value):

    if not isinstance(value, str) or not value.strip():
        return None

    parser = ImageURLParser()
    parser.feed(value)

    candidates = (
        parser.urls
        + ["".join(parser.text).strip()]
        + [value.strip()]
    )

    allowed_hosts = {
        "danubeproperties.com",
        "www.danubeproperties.com",
    }

    allowed_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
    }

    for candidate in candidates:

        url = unescape(candidate).strip()
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in allowed_hosts
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            continue

        if not parsed.path.lower().endswith(
            tuple(allowed_extensions)
        ):
            continue

        return url

    return None


class ProjectInformationHandler:

    def __init__(
        self,
        *,
        inventory_snapshot,
        inventory_token: str,
        access_token: str,
    ):

        self.snapshot = inventory_snapshot
        self.inventory_token = inventory_token
        self.access_token = access_token

        # Existing project information API.
        self.connector = ProjectInformationConnector()

        # NEW: Project coordinates API.
        # Uses project_id to retrieve latitude/longitude.
        self.coordinates_connector = (
            ProjectCoordinatesConnector()
        )

        # KEEP: OSF Portfolio API for 3D tours.
        self.tour_connector = OSFPortfolioConnector()

        self.templates = TemplateService()

    def failure(self, message):

        return HandlerResult(
            intent="project_information",
            messages=[message],
            has_data=False,
        )

    def resolve_project(self, intent, projects):

        identifiers = [
            ("project_id", intent.project_id),
            ("project_number", intent.project_number),
            ("project_name", intent.project_name),
        ]

        candidate_sets = []

        for field, value in identifiers:

            if not value:
                continue

            key = normalize(value)

            exact = [
                project
                for project in projects
                if normalize(
                    getattr(project, field, None)
                ) == key
            ]

            # Permit unique shortened project names.
            if not exact and field == "project_name":

                exact = [
                    project
                    for project in projects
                    if key in normalize(
                        project.project_name
                    )
                ]

            if not exact:
                return None, "Project not found."

            candidate_sets.append({
                project.project_id
                for project in exact
            })

        unit_identifiers = [
            intent.unit_id,
            intent.unit_name,
            intent.unit_number,
        ]

        if any(unit_identifiers):

            matched_units = []

            for unit in self.snapshot.units:

                values = [
                    unit.unit_id,
                    unit.unit_name,
                    unit.unit_code,
                ]

                if any(
                    normalize(identifier)
                    == normalize(value)
                    for identifier in unit_identifiers
                    if identifier
                    for value in values
                    if value
                ):
                    matched_units.append(unit)

            if not matched_units:
                return None, (
                    "I couldn't find that unit in your "
                    "authorized inventory."
                )

            candidate_sets.append({
                unit.project_id
                for unit in matched_units
                if unit.project_id
            })

        if not candidate_sets:
            return None, (
                "Please specify a project name, "
                "number, ID, or unit."
            )

        matching_ids = set.intersection(
            *candidate_sets
        )

        matches = [
            project
            for project in projects
            if project.project_id in matching_ids
        ]

        if len(matches) == 1:
            return matches[0], None

        if len(matches) > 1:
            return None, (
                "Multiple projects match your request. "
                "Please specify the exact project."
            )

        return None, (
            "No project matches the supplied identifiers."
        )

    @staticmethod
    def project_summary(project):

        return {
            "project_name": project.project_name,
            "project_id": project.project_id,
            "project_number": project.project_number,
            "location": project.location,
            "starting_price_aed": (
                project.starting_price
            ),
            "total_units": project.total_units,
            "bedrooms": (
                project.bedrooms_categories
            ),
            "apartments": project.apartments,
            "payment_plan": project.payment_plan,
            "construction_status": (
                project.construction_status
            ),
            "handover_date": project.handover_date,
            "completion_date": (
                project.completion_date
            ),
            "project_configuration": (
                project.project_configuration
            ),
            "service_charge": (
                project.service_charge
            ),
            "amenities": project.amenities,
            "places_nearby": (
                project.places_nearby
            ),
        }


    async def get_project_map_url(self, project):

        project_id = project.project_id

        if not project_id:
            return None

        try:

            # Step 1: Call new Project Coordinates API.
            coordinates = (
                await self.coordinates_connector
                .fetch_coordinates(
                    project_id=str(project_id),
                    access_token=self.access_token,
                )
            )

            if not coordinates:

                logger.info(
                    "PROJECT_COORDINATES_NOT_FOUND | "
                    "project_id=%s",
                    project_id,
                )

                return None

            latitude = coordinates.get(
                "latitude"
            )

            longitude = coordinates.get(
                "longitude"
            )

            if latitude is None or longitude is None:

                logger.info(
                    "PROJECT_COORDINATES_MISSING | "
                    "project_id=%s",
                    project_id,
                )

                return None

            # Step 2: Generate Google Maps URL.
            # The paid Google API key is used inside
            # generate_map_url_from_coordinates().
            secrets = await load_application_secrets()

            map_url = (
                await generate_map_url_from_coordinates(
                    latitude=latitude,
                    longitude=longitude,
                    google_api_key=secrets.google_maps_api_key.get_secret_value(),
                )
            )

            logger.info(
                "PROJECT_MAP_URL_GENERATED | "
                "project_id=%s",
                project_id,
            )

            return map_url

        except Exception:

            logger.exception(
                "PROJECT_MAP_GENERATION_FAILED | "
                "project_id=%s",
                project_id,
            )

            # Map failure should not prevent
            # project information from displaying.
            return None

    async def get_project_map_urls(self, projects):

        # Limit concurrent calls to external APIs.
        semaphore = asyncio.Semaphore(5)

        async def fetch_one(project):

            async with semaphore:

                map_url = await (
                    self.get_project_map_url(project)
                )

                return (
                    str(project.project_id),
                    map_url,
                )

        results = await asyncio.gather(
            *[
                fetch_one(project)
                for project in projects
            ]
        )

        return dict(results)


    def render_cards(
        self,
        projects,
        map_urls=None,
    ):

        cards = []

        map_urls = map_urls or {}

        for project in projects:

            # Direct project_id lookup.
            # No project-name normalization.
            # No hardcoded aliases.
            map_url = map_urls.get(
                str(project.project_id)
            )

            html = self.templates.render(
                "project_information_card.html.j2",

                project_name=project.project_name,

                image_url=safe_image_url(
                    project.project_image
                ),

                starting_price=(
                    project.starting_price
                ),

                total_units=project.total_units,

                location=project.location,

                map_url=map_url,
            )

            cards.append({
                "card_type": (
                    "project_information"
                ),
                "html": html,
            })

        return cards

    async def handle_project_tour(
        self,
        intent,
        projects,
    ):

        """
        Fetch and render the 3D tour of a project.

        OSF Portfolio API is retained for this.
        """

        project, error = self.resolve_project(
            intent,
            projects,
        )

        if error:
            return self.failure(error)

        # Fetch OSF Portfolio API.
        try:

            portfolio = (
                await self.tour_connector
                .fetch_portfolio()
            )

        except Exception:

            logger.exception(
                "PROJECT_TOUR_API_FAILED"
            )

            return self.failure(
                "The project tour is temporarily "
                "unavailable. Please try again."
            )

        # Build existing video lookup.
        tour_lookup = (
            build_project_tour_lookup(
                portfolio
            )
        )

        # Keep existing tour-name matching.
        project_key = (
            normalize_map_project_name(
                project.project_name
            )
        )

        video_url = tour_lookup.get(
            project_key
        )

        if not video_url:

            logger.info(
                "PROJECT_TOUR_NOT_FOUND | "
                "project_id=%s",
                project.project_id,
            )

            return self.failure(
                f"A 3D tour is not currently "
                f"available for "
                f"{project.project_name}."
            )

        html = self.templates.render(
            "project_tour.html.j2",
            project_id=project.project_id,
            project_name=project.project_name,
            video_url=video_url,
        )

        logger.info(
            "PROJECT_TOUR_FOUND | "
            "project_id=%s",
            project.project_id,
        )

        return HandlerResult(
            intent="project_information",

            html_blocks=[
                {
                    "card_type": "project_tour",
                    "html": html,
                }
            ],

            files=[],

            messages=[],

            generation_context={
                "service": (
                    "project_information"
                ),
                "operation": "tour",
                "result_count": 1,
                "project_name": (
                    project.project_name
                ),
                "tour_available": True,
                "projects": [
                    self.project_summary(
                        project
                    )
                ],
            },

            has_data=True,
        )

    @staticmethod
    def display_value(value):

        """Convert API values to display text safely."""

        if value is None or value == "":
            return None

        if isinstance(value, dict):
            return None

        if isinstance(
            value,
            (list, tuple, set),
        ):

            values = [
                str(item).strip()
                for item in value
                if isinstance(
                    item,
                    (str, int, float),
                )
                and str(item).strip()
            ]

            return (
                ", ".join(values)
                if values
                else None
            )

        return str(value).strip() or None

    def render_project_details(self, project):

        """Render one Figma-style project details card."""

        html = self.templates.render(
            "project_details.html.j2",

            project_name=project.project_name,

            location=self.display_value(
                project.location
            ),

            project_configuration=(
                self.display_value(
                    project.project_configuration
                )
            ),

            bedrooms=self.display_value(
                project.bedrooms_categories
            ),

            total_units=project.total_units,

            amenities=self.display_value(
                project.amenities
            ),

            completion_date=self.display_value(
                project.completion_date
            ),

            starting_price=self.display_value(
                project.starting_price
            ),

            payment_plan=self.display_value(
                project.payment_plan
            ),

            construction_status=self.display_value(
                project.construction_status
            ),

            handover_date=self.display_value(
                project.handover_date
            ),

            description=None,

            details_url=None,

            available_units_url=None,
        )

        return [{
            "card_type": "project_details",
            "html": html,
        }]


    async def handle(self, intent):

        try:

            # Step 1: Fetch authorized project data.
            projects = (
                await self.connector.fetch_projects(
                    inventory_token=(
                        self.inventory_token
                    ),
                    access_token=(
                        self.access_token
                    ),
                )
            )

            projects = [
                project
                for project in projects
                if (
                    project.project_id
                    and project.project_name
                )
            ]

            operation = (
                intent.project_operation
                or "details"
            )

            # Step 2: 3D tour uses OSF Portfolio API.
            if operation == "tour":

                return await (
                    self.handle_project_tour(
                        intent,
                        projects,
                    )
                )

            # Step 3: Select projects.
            elif operation == "latest":

                limit = min(
                    max(
                        intent.project_limit or 3,
                        1,
                    ),
                    20,
                )

                selected = projects[:limit]

            elif operation == "list":

                limit = min(
                    max(
                        intent.project_limit or 5,
                        1,
                    ),
                    20,
                )

                selected = projects[:limit]

            elif operation == "location_search":

                location = normalize(
                    intent.project_location
                )

                if not location:

                    return self.failure(
                        "Which location would "
                        "you like to search?"
                    )

                selected = [
                    project
                    for project in projects
                    if location in normalize(
                        project.location
                    )
                ][:20]

            else:

                project, error = (
                    self.resolve_project(
                        intent,
                        projects,
                    )
                )

                if error:
                    return self.failure(error)

                selected = [project]

            if not selected:

                return self.failure(
                    "No matching Danube "
                    "projects were found."
                )

            # Step 4: Prepare project summaries.
            summaries = [
                self.project_summary(
                    project
                )
                for project in selected
            ]

            # Step 5: Generate map URLs only for
            # operations that render project list cards.
            map_urls = {}

            if operation != "details":

                map_urls = (
                    await self.get_project_map_urls(
                        selected
                    )
                )

            # Step 6: Return existing HandlerResult.
            return HandlerResult(
                intent="project_information",

                html_blocks=(
                    self.render_project_details(
                        selected[0]
                    )
                    if operation == "details"
                    else self.render_cards(
                        selected,
                        map_urls=map_urls,
                    )
                ),

                files=[],

                messages=[],

                generation_context={
                    "service": (
                        "project_information"
                    ),

                    "operation": operation,

                    "result_count": len(selected),

                    "requested_location": (
                        intent.project_location
                    ),

                    "projects": summaries,
                },

                has_data=True,
            )

        except ProjectInformationAPIError:

            logger.exception(
                "PROJECT_INFORMATION_FETCH_FAILED"
            )

            return self.failure(
                "Project information is temporarily "
                "unavailable. Please try again."
            )
