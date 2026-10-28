
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

DEBUG_FILE = Path("debug/bank_details_debug.jsonl")
_LOCK = threading.Lock()


def bank_debug(stage: str, data):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "data": data,
    }

    # Print to terminal
    print(
        "\n[BANK DEBUG]",
        json.dumps(record, indent=2, default=str),
        flush=True,
    )

    # Save to separate debug file
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
