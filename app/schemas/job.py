from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.domain.job_status import JobStatus


class JobProcessRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class JobInput(BaseModel):
    text: str | None = None
    notification_id: UUID | None = None
    recipient: str | None = None
    external_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class JobResult(BaseModel):
    processed_text: str | None = None
    document_id: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    recommendation_count: int | None = None
    notification_id: UUID | None = None
    provider: str | None = None
    provider_message_id: str | None = None
    provider_status: str | None = None
    provider_response: dict[str, Any] | None = None
    completed_at: datetime


class JobErrorDetail(BaseModel):
    type: str
    message: str
    phase: str | None = None


class JobProgressEvent(BaseModel):
    phase: str
    progress_percentage: int = Field(ge=0, le=100)
    message: str | None = None
    progress_detail: dict[str, Any] | None = None
    status: JobStatus
    recorded_at: datetime


class JobQueuedResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    input: JobInput
    message: str | None = None
    result: JobResult | None = None
    error: str | JobErrorDetail | None = None
    phase: str | None = None
    progress_percentage: int | None = Field(default=None, ge=0, le=100)
    progress_detail: dict[str, Any] | None = None
    progress_history: list[JobProgressEvent] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
