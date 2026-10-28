import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FIXTURE_DIR = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "inventory"
)


def load_local_json(filename: str) -> dict:
    file_path = FIXTURE_DIR / filename

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Inventory fixture not found: {file_path}"
        )

    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected JSON object in {filename}"
        )

    return data