
import json
import re
from typing import Any


PAYMENT_SELECTION_TTL = 1800  # 30 minutes


def payment_selection_key(user_id: str, session_id: str) -> str:
    return f"danube:payment_plan:pending:{user_id}:{session_id}"


async def save_pending_payment_selection(
    redis_client,
    user_id: str,
    session_id: str,
    unit_id: str,
    unit_name: str,
    plans: list[dict],
) -> None:
    """
    Save the list of payment plans awaiting user selection.
    Only IDs and names are stored.
    """
    payload = {
        "type": "payment_plan_selection",
        "unit_id": unit_id,
        "unit_name": unit_name,
        "plans": [
            {
                "id": str(plan["Id"]),
                "name": str(plan["Name"]),
            }
            for plan in plans
            if plan.get("Id") and plan.get("Name")
        ],
    }

    key = payment_selection_key(user_id, str(session_id))

    await redis_client.set(
        key,
        json.dumps(payload),
        ex=PAYMENT_SELECTION_TTL,
    )


async def load_pending_payment_selection(
    redis_client,
    user_id: str,
    session_id: str,
) -> dict[str, Any] | None:
    key = payment_selection_key(user_id, str(session_id))

    raw = await redis_client.get(key)

    if not raw:
        return None

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        await redis_client.delete(key)
        return None

    if (
        not isinstance(payload, dict)
        or payload.get("type") != "payment_plan_selection"
        or not isinstance(payload.get("plans"), list)
    ):
        await redis_client.delete(key)
        return None

    return payload


async def clear_pending_payment_selection(
    redis_client,
    user_id: str,
    session_id: str,
) -> None:
    await redis_client.delete(
        payment_selection_key(user_id, str(session_id))
    )


def normalize_plan_name(value: str) -> str:
    return " ".join(value.casefold().split())



def match_selected_plan(
    message: str,
    plans: list[dict],
) -> dict | None:
    """
    Match a payment plan using:
    - Exact plan name
    - Numeric option: 1, 2, 3
    - Option number: option 1, plan 2
    - Ordinal words: first, second, third
    - Ordinal numbers: 1st, 2nd, 3rd

    Returns None for invalid or ambiguous selections.
    """

    normalized = normalize_plan_name(message)

    # 1. Exact payment plan name
    matches = [
        plan
        for plan in plans
        if normalize_plan_name(plan["name"]) == normalized
    ]

    if len(matches) == 1:
        return matches[0]

    if matches:
        return None

    # 2. Ordinal words
    ordinal_words = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
        "eleventh": 11,
        "twelfth": 12,
        "thirteenth": 13,
        "fourteenth": 14,
        "fifteenth": 15,
        "sixteenth": 16,
        "seventeenth": 17,
        "eighteenth": 18,
        "nineteenth": 19,
        "twentieth": 20,
        "last": len(plans),
    }

    ordinal_match = re.fullmatch(
        r"(?:the\s+)?"
        r"(?:option\s+|plan\s+)?"
        r"([a-z]+)"
        r"(?:\s+(?:option|plan))?",
        normalized,
    )

    if ordinal_match:
        word = ordinal_match.group(1)
        index = ordinal_words.get(word)

        if index is not None and 1 <= index <= len(plans):
            return plans[index - 1]

    # 3. Numeric selection: 1, option 2, plan 3
    numbered = re.fullmatch(
        r"(?:the\s+)?"
        r"(?:option\s+|plan\s+|number\s+)?"
        r"(\d+)"
        r"(?:st|nd|rd|th)?"
        r"(?:\s+(?:option|plan))?",
        normalized,
    )

    if numbered:
        index = int(numbered.group(1)) - 1

        if 0 <= index < len(plans):
            return plans[index]

    return None

