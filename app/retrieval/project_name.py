import re
import unicodedata


def normalize_project_name(value: str | None) -> str:
    if not value:
        return ""

    value = unicodedata.normalize("NFKC", value)
    value = value.casefold().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+by\s+danube$", "", value)

    return " ".join(value.split())


def resolve_project_name(
    requested_name: str | None,
    available_projects: list[str],
) -> str | None:

    if not requested_name:
        return None

    requested = normalize_project_name(requested_name)

    matches = [
        name
        for name in available_projects
        if normalize_project_name(name) == requested
    ]

    if len(matches) == 1:
        return matches[0]

    return None