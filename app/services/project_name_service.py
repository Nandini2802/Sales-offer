import re
import unicodedata


def normalize_project_name(value: str | None) -> str:
    if not value:
        return ""

    text = unicodedata.normalize("NFKC", value).casefold().strip()

    text = re.sub(r"\s+by\s+danube\s*$", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())