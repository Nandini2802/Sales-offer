from pydantic import BaseModel, Field


class MarketingFile(BaseModel):
    name: str
    download_url: str
    file_size_bytes: int | None = None
    language: str | None = None


class MarketingAsset(BaseModel):
    project: str
    asset_type: str

    files: list[MarketingFile] = Field(
        default_factory=list
    )

    zip_url: str | None = None
    total_files: int = 0