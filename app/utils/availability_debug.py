import json
import threading
from datetime import datetime, timezone
from pathlib import Path

DEBUG_FILE = Path("debug/availability_debug.jsonl")
_LOCK = threading.Lock()


def availability_debug(stage: str, data):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "data": data,
    }

    print(
        "\n[AVAILABILITY DEBUG]",
        json.dumps(record, indent=2, default=str),
        flush=True,
    )

    DEBUG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _LOCK:
        with DEBUG_FILE.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(record, default=str)
                + "\n"
            )