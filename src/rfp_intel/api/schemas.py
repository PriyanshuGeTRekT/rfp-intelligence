"""Request and response models for the REST API."""

from pydantic import BaseModel, Field


class IndexRequest(BaseModel):
    path: str = Field(description="Bid folder, relative to the data directory")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    bid_id: str | None = None


class Health(BaseModel):
    status: str
    version: str
