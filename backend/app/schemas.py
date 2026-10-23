from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AssignmentStatus = Literal["Not started", "In progress", "Completed"]


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=20)
    color: str = Field(default="#4f46e5", pattern=r"^#[0-9a-fA-F]{6}$")


class SubjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class SubjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    color: str
    created_at: datetime


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject_id: int
    due_date: date
    status: AssignmentStatus = "Not started"
    platform: str = Field(default="Manual entry", max_length=100)
    description: str | None = None


class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    subject_id: int | None = None
    due_date: date | None = None
    status: AssignmentStatus | None = None
    platform: str | None = Field(default=None, max_length=100)
    description: str | None = None


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject_id: int
    due_date: date
    status: str
    platform: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class AssistantRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class AssistantResponse(BaseModel):
    answer: str
    mode: Literal["deterministic"]
    assignment_ids: list[int]


class TimetableUploadRead(BaseModel):
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    storage_provider: str
    uploaded_at: datetime
    file_url: str
