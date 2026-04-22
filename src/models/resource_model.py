from pydantic import BaseModel, Field


class Resource(BaseModel):
    """Basic resource description used by the API."""

    id: int = Field(..., description="Unique identifier for the resource")
    title: str = Field(..., description="Human-readable title")
    url: str = Field(..., description="Link to the resource")
    summary: str | None = Field(None, description="Short description")
