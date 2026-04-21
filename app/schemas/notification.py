from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.domain.notification_status import NotificationStatus
from app.models.notification import Notification


PhoneNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=8, max_length=20, pattern=r"^\d+$"),
]


class NotificationCreateRequest(BaseModel):
    external_id: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] = None
    recipient: PhoneNumber
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)]
    priority: Literal["low", "normal", "high"] = "normal"
    metadata: dict[str, Any] | None = None


class NotificationCreateResponse(BaseModel):
    notification_id: UUID
    job_id: UUID | None
    status: NotificationStatus
    already_exists: bool = False


class NotificationResponse(BaseModel):
    id: UUID
    external_id: str | None
    recipient: str
    message: str
    type: str
    priority: str
    status: NotificationStatus
    provider: str
    provider_message_id: str | None
    provider_response: dict[str, Any] | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None
    attempt_count: int
    job_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None = None
    failed_at: datetime | None = None

    @classmethod
    def from_model(cls, notification: Notification) -> "NotificationResponse":
        return cls(
            id=notification.id,
            external_id=notification.external_id,
            recipient=notification.recipient,
            message=notification.message,
            type=notification.notification_type,
            priority=notification.priority,
            status=NotificationStatus(notification.status),
            provider=notification.provider,
            provider_message_id=notification.provider_message_id,
            provider_response=notification.provider_response,
            error_message=notification.error_message,
            metadata=notification.notification_metadata,
            attempt_count=notification.attempt_count,
            job_id=notification.last_job_id,
            created_at=notification.created_at,
            updated_at=notification.updated_at,
            sent_at=notification.sent_at,
            failed_at=notification.failed_at,
        )


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(default_factory=list)
    page: int
    limit: int
    total: int
