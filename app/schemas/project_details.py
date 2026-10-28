from pydantic import BaseModel, Field


class ProjectHighlight(BaseModel):
    icon: str
    text: str


class ProjectDetailsContent(BaseModel):
    project_name: str
    introduction: str
    highlights: list[ProjectHighlight] = Field(
        default_factory=list
    )
    description: str | None = None