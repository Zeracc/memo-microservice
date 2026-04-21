from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


@dataclass(slots=True)
class NotificationListFilters:
    status: str | None = None
    recipient: str | None = None
    external_id: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = 1
    limit: int = 20


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        external_id: str | None,
        recipient: str,
        message: str,
        priority: str,
        notification_type: str = "whatsapp",
        provider: str = "uazapi",
        metadata: dict[str, Any] | None = None,
        status: str = "pending",
        last_job_id: UUID | None = None,
    ) -> Notification:
        notification = Notification(
            external_id=external_id,
            recipient=recipient,
            message=message,
            priority=priority,
            notification_type=notification_type,
            provider=provider,
            notification_metadata=metadata,
            status=status,
            last_job_id=last_job_id,
        )
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        return await self.session.get(Notification, notification_id)

    async def get_by_external_id(self, external_id: str) -> Notification | None:
        statement = select(Notification).where(Notification.external_id == external_id)
        return await self.session.scalar(statement)

    async def list(
        self,
        filters: NotificationListFilters,
    ) -> tuple[list[Notification], int]:
        conditions = []
        if filters.status:
            conditions.append(Notification.status == filters.status)
        if filters.recipient:
            conditions.append(Notification.recipient == filters.recipient)
        if filters.external_id:
            conditions.append(Notification.external_id == filters.external_id)
        if filters.created_from:
            conditions.append(Notification.created_at >= self._ensure_utc(filters.created_from))
        if filters.created_to:
            conditions.append(Notification.created_at <= self._ensure_utc(filters.created_to))

        total_statement = select(func.count()).select_from(Notification)
        statement = select(Notification)

        if conditions:
            total_statement = total_statement.where(*conditions)
            statement = statement.where(*conditions)

        statement = statement.order_by(desc(Notification.created_at)).offset(
            (filters.page - 1) * filters.limit
        ).limit(filters.limit)

        total = int((await self.session.execute(total_statement)).scalar_one())
        notifications = list((await self.session.scalars(statement)).all())
        return notifications, total

    async def set_job_id(self, notification_id: UUID, job_id: UUID | str) -> Notification | None:
        notification = await self.get_by_id(notification_id)
        if notification is None:
            return None

        notification.last_job_id = UUID(str(job_id))
        notification.updated_at = self._utc_now()
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def update_status(
        self,
        notification_id: UUID,
        *,
        status: str,
        error_message: str | None = None,
        provider_message_id: str | None = None,
        provider_response: dict[str, Any] | None = None,
        sent_at: datetime | None = None,
        failed_at: datetime | None = None,
    ) -> Notification | None:
        notification = await self.get_by_id(notification_id)
        if notification is None:
            return None

        notification.status = status
        notification.error_message = error_message
        notification.provider_message_id = provider_message_id
        notification.provider_response = provider_response
        notification.sent_at = sent_at
        notification.failed_at = failed_at
        notification.updated_at = self._utc_now()

        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def increment_attempt_count(self, notification_id: UUID) -> Notification | None:
        notification = await self.get_by_id(notification_id)
        if notification is None:
            return None

        notification.attempt_count += 1
        notification.updated_at = self._utc_now()
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
