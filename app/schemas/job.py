from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, StringConstraints


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobProcessRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class JobInput(BaseModel):
    text: str


class JobResult(BaseModel):
    processed_text: str


class JobQueuedResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    input: JobInput
    result: JobResult | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
