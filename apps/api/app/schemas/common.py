import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class Message(BaseModel):
    message: str


class ActivityOut(ORM):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    kind: str
    message: str
    data: dict
    actor_id: uuid.UUID | None
    actor_name: str | None = None
    customer_visible: bool
    created_at: datetime


class JobOut(ORM):
    id: uuid.UUID
    kind: str
    status: str
    progress: int
    result: dict
    error: str | None
    created_at: datetime
    updated_at: datetime
