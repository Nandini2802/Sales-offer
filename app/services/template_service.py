from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_DIR = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "cards"
)


class TemplateService:

    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(
                enabled_extensions=("html", "j2"),
                default_for_string=True,
            ),
        )

    def render(
        self,
        template_name: str,
        **context,
    ) -> str:

        template = self.env.get_template(template_name)

        return template.render(**context)

    def render_marketing_asset(self, asset) -> str:

        if asset.asset_type == "brochures":
            return self.render(
                "brochure.html.j2",
                project=asset.project,
                files=[
                    item.model_dump()
                    for item in asset.files
                ],
                zip_url=None,
            )

        if asset.asset_type in {"videos", "walkthrough"}:
            return self.render(
                "video.html.j2",
                project=asset.project,
                files=[
                    item.model_dump()
                    for item in asset.files
                ],
                zip_url=None,
            )

        if asset.asset_type == "floor-plans":
            return self.render(
                "floor_plan.html.j2",
                project=asset.project,
                total_images=asset.total_files,
                zip_url=asset.zip_url,
            )

        labels = {
            "interiors": "Interior Images",
            "exteriors": "Exterior Images",
            "amenities": "Amenities",
            "social-media": "Social Media",
            "factsheet": "Factsheet",
            "other": "Other Materials",
            "all": "All Marketing Materials",
        }

        if asset.asset_type not in labels:
            raise ValueError(
                f"Unsupported marketing asset: {asset.asset_type}"
            )

        return self.render(
            "zip_download.html.j2",
            project=asset.project,
            label=labels[asset.asset_type],
            total_files=asset.total_files,
            zip_url=asset.zip_url,
        )