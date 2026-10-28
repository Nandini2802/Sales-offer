from dataclasses import dataclass, field
from typing import Any


@dataclass
class HandlerResult:
    intent: str

    # Verified data for LLM 2
    generation_context: dict[str, Any] = field(
        default_factory=dict
    )

    # HTML cards sent through SSE
    html_blocks: list[dict[str, str]] = field(
        default_factory=list
    )

    # Files included in final ChatResponse
    files: list[dict[str, Any]] = field(
        default_factory=list
    )

    # Clarifications, unavailable data, etc.
    messages: list[str] = field(
        default_factory=list
    )

    # Whether verified business data was found
    has_data: bool = False
