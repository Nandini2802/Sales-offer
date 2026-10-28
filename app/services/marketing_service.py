import re
from urllib.parse import urlparse

from app.services.api_cache_service import (
    get_cached_marketing_data,
)
from app.schemas.marketing import (
    MarketingAsset,
    MarketingFile,
)


FOLDER_ALIASES = {
    "brochure": "brochures",
    "brochures": "brochures",
    "video": "videos",
    "videos": "videos",
    "walkthrough": "walkthrough",
    "walkthrough video": "walkthrough",
    "floor plan": "floor-plans",
    "floor plans": "floor-plans",
    "floor_plan": "floor-plans",
    "gallery": "interiors",
    "interior": "interiors",
    "interiors": "interiors",
    "exterior": "exteriors",
    "exteriors": "exteriors",
    "amenities": "amenities",
    "social media": "social-media",
    "social-media": "social-media",
    "factsheet": "factsheet",
    "fact sheet": "factsheet",
    "other": "other",
    "all": "all",
}

INDIVIDUAL_FILE_FOLDERS = {
    "brochures",
    "videos",
    "walkthrough",
}

ALLOWED_FILE_HOSTS = {
    "d39mr55n259x6c.cloudfront.net",
}

ALLOWED_ZIP_HOSTS = {
    "middleware.danubeproperties.com",
}


def normalize_project_name(name: str) -> str:
    value = name.casefold().strip()

    value = re.sub(
        r"\bby\s+danube\b",
        "",
        value,
    )

    return re.sub(r"[^a-z0-9]", "", value)


def safe_url(value: str | None, hosts: set[str]) -> str | None:
    if not isinstance(value, str):
        return None

    parsed = urlparse(value.strip())

    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    return value.strip()


class MarketingService:

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_assets(
        self,
        project_name: str,
        asset_types: list[str],
        language: str | None = None,
    ) -> list[MarketingAsset]:

        response = await get_cached_marketing_data(
            self.redis
        )

        if not isinstance(response, dict):
            raise RuntimeError(
                "Marketing catalog is unavailable"
            )

        # Existing cache helper returns the outer
        # response["data"], which contains another
        # "data" object in your current cache.
        payload = response.get("data", response)

        if not isinstance(payload, dict):
            raise RuntimeError(
                "Invalid marketing catalog structure"
            )

        projects = payload.get("marketingCollateral", [])

        if not isinstance(projects, list):
            raise RuntimeError(
                "Invalid marketing project list"
            )

        requested_name = normalize_project_name(
            project_name
        )

        project = next(
            (
                item
                for item in projects
                if isinstance(item, dict)
                and normalize_project_name(
                    str(item.get("project_title", ""))
                ) == requested_name
            ),
            None,
        )

        if project is None:
            return []

        result = []

        for requested_type in dict.fromkeys(asset_types):

            folder = FOLDER_ALIASES.get(
                requested_type.casefold().strip()
            )

            if folder is None:
                continue

            download_urls = project.get(
                "download_urls", {}
            ) or {}

            if folder == "all":
                zip_url = safe_url(
                    (
                        download_urls.get(
                            "download_all", {}
                        ) or {}
                    ).get("url"),
                    ALLOWED_ZIP_HOSTS,
                )

                if zip_url:
                    result.append(
                        MarketingAsset(
                            project=project["project_title"],
                            asset_type="all",
                            zip_url=zip_url,
                        )
                    )

                continue

            files = []

            # API returns nested lists of files
            for group in project.get(
                "marketing_collateral_row_assets", []
            ) or []:

                if not isinstance(group, list):
                    continue

                for item in group:

                    if not isinstance(item, dict):
                        continue

                    if item.get("folder_key") != folder:
                        continue

                    url = safe_url(
                        item.get("url"),
                        ALLOWED_FILE_HOSTS,
                    )

                    if not url:
                        continue

                    name = str(
                        item.get("original_name")
                        or item.get("file_name")
                        or "Download"
                    )

                    files.append(
                        MarketingFile(
                            name=name,
                            download_url=url,
                            file_size_bytes=(
                                item.get("size")
                                if isinstance(
                                    item.get("size"), int
                                )
                                and item["size"] >= 0
                                else None
                            ),
                        )
                    )

            # Explicit language filtering requires
            # verified language metadata. The API
            # sample has filenames, not a language field.
            if language:
                # Do not guess language from arbitrary
                # filename fragments.
                pass

            folder_info = (
                download_urls.get("folders", {}) or {}
            ).get(folder, {}) or {}

            zip_url = safe_url(
                folder_info.get("url"),
                ALLOWED_ZIP_HOSTS,
            )

            if folder in INDIVIDUAL_FILE_FOLDERS:
                # Individual brochure/video links
                if not files:
                    continue

                result.append(
                    MarketingAsset(
                        project=project["project_title"],
                        asset_type=folder,
                        files=files,
                        total_files=len(files),
                    )
                )

            else:
                # Other assets use ZIP downloads
                if not zip_url:
                    continue

                result.append(
                    MarketingAsset(
                        project=project["project_title"],
                        asset_type=folder,
                        zip_url=zip_url,
                        total_files=len(files),
                    )
                )

        return result