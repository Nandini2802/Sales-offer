
from pydantic import BaseModel, Field, ConfigDict


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str = Field(
        description=(
            "Short factual response to the user, "
            "in the detected language."
        )
    )

    followups: list[str] = Field(
        description=(
            "Zero to three relevant follow-up "
            "questions in the detected language."
        )
    )
