from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError

from app.domain.notification_status import NotificationStatus
from app.repositories.notification_repository import NotificationListFilters, NotificationRepository
from app.schemas.job import JobInput
from app.schemas.notification import (
    NotificationCreateRequest,
    NotificationCreateResponse,
    NotificationListResponse,
    NotificationResponse,
)
from app.services.job_service import JobService


logger = logging.getLogger(__name__)

TaskDispatcher = Callable[[UUID, UUID], str | None]


class NotificationService:
    def __init__(
        self,
        notification_repository: NotificationRepository,
        job_service: JobService,
        task_dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.notification_repository = notification_repository
        self.job_service = job_service
        self.task_dispatcher = task_dispatcher

    async def create_notification(
        self,
        payload: NotificationCreateRequest,
    ) -> NotificationCreateResponse:
        logger.info(
            "Creating notification external_id=%s recipient=%s priority=%s",
            payload.external_id,
            payload.recipient,
            payload.priority,
        )
        if payload.external_id:
            existing = await self.notification_repository.get_by_external_id(payload.external_id)
            if existing is not None:
                logger.info(
                    "Notification idempotency hit external_id=%s notification_id=%s job_id=%s status=%s",
                    payload.external_id,
                    existing.id,
                    existing.last_job_id,
                    existing.status,
                )
                return NotificationCreateResponse(
                    notification_id=existing.id,
                    job_id=existing.last_job_id,
                    status=NotificationStatus(existing.status),
                    already_exists=True,
                )

        try:
            notification = await self.notification_repository.create(
                external_id=payload.external_id,
                recipient=payload.recipient,
                message=payload.message,
                priority=payload.priority,
                metadata=payload.metadata,
                status=NotificationStatus.PENDING.value,
            )
        except IntegrityError:
            await self.notification_repository.session.rollback()
            existing = None
            if payload.external_id:
                existing = await self.notification_repository.get_by_external_id(payload.external_id)
            if existing is None:
                raise
            logger.info(
                "Notification idempotency recovered after integrity error external_id=%s notification_id=%s",
                payload.external_id,
                existing.id,
            )
            return NotificationCreateResponse(
                notification_id=existing.id,
                job_id=existing.last_job_id,
                status=NotificationStatus(existing.status),
                already_exists=True,
            )

        logger.info(
            "Notification persisted notification_id=%s external_id=%s status=%s",
            notification.id,
            notification.external_id,
            notification.status,
        )

        try:
            queued_job = await self.job_service.create_tracking_job(
                JobInput(
                    notification_id=notification.id,
                    recipient=notification.recipient,
                    external_id=notification.external_id,
                    payload={"provider": notification.provider, "type": notification.notification_type},
                ),
                message="Notificacao enfileirada com sucesso.",
            )
        except RedisError:
            await self.mark_failed(notification.id, error_message="Falha ao criar job de processamento.")
            raise

        notification_id = notification.id
        notification = await self.notification_repository.set_job_id(notification_id, queued_job.job_id)
        if notification is None:
            raise RuntimeError(f"Notification {notification_id} not found after job creation")

        if self.task_dispatcher is None:
            raise RuntimeError("Task dispatcher is not configured")

        try:
            task_id = self.task_dispatcher(notification.id, queued_job.job_id)
            logger.info(
                "Notification enqueued: notification_id=%s job_id=%s celery_task_id=%s",
                notification.id,
                queued_job.job_id,
                task_id,
            )
        except Exception as exc:
            await self.mark_failed(
                notification.id,
                error_message=f"Falha ao enfileirar task Celery: {exc}",
            )
            await self.job_service.mark_failed(
                queued_job.job_id,
                {
                    "type": exc.__class__.__name__,
                    "message": str(exc) or exc.__class__.__name__,
                    "phase": "queueing",
                },
                message="Falha ao enfileirar envio da notificacao.",
                phase="queueing",
            )
            raise

        return NotificationCreateResponse(
            notification_id=notification.id,
            job_id=notification.last_job_id,
            status=NotificationStatus(notification.status),
            already_exists=False,
        )

    async def get_notification(self, notification_id: UUID) -> NotificationResponse | None:
        notification = await self.notification_repository.get_by_id(notification_id)
        if notification is None:
            return None
        return NotificationResponse.from_model(notification)

    async def list_notifications(self, filters: NotificationListFilters) -> NotificationListResponse:
        notifications, total = await self.notification_repository.list(filters)
        return NotificationListResponse(
            items=[NotificationResponse.from_model(notification) for notification in notifications],
            page=filters.page,
            limit=filters.limit,
            total=total,
        )

    async def mark_processing(self, notification_id: UUID) -> NotificationResponse | None:
        notification = await self.notification_repository.update_status(
            notification_id,
            status=NotificationStatus.PROCESSING.value,
            error_message=None,
            failed_at=None,
        )
        if notification is not None:
            logger.info("Notification processing notification_id=%s", notification_id)
        return self._as_response(notification)

    async def mark_retrying(
        self,
        notification_id: UUID,
        *,
        error_message: str,
    ) -> NotificationResponse | None:
        notification = await self.notification_repository.update_status(
            notification_id,
            status=NotificationStatus.PENDING.value,
            error_message=error_message,
            failed_at=None,
        )
        if notification is not None:
            logger.warning(
                "Notification retry scheduled notification_id=%s error=%s",
                notification_id,
                error_message,
            )
        return self._as_response(notification)

    async def mark_sent(
        self,
        notification_id: UUID,
        *,
        provider_message_id: str | None,
        provider_response: dict[str, object] | None,
    ) -> NotificationResponse | None:
        notification = await self.notification_repository.update_status(
            notification_id,
            status=NotificationStatus.SENT.value,
            error_message=None,
            provider_message_id=provider_message_id,
            provider_response=provider_response,
            sent_at=self._utc_now(),
            failed_at=None,
        )
        if notification is not None:
            logger.info(
                "Notification sent notification_id=%s provider_message_id=%s",
                notification_id,
                provider_message_id,
            )
        return self._as_response(notification)

    async def mark_failed(
        self,
        notification_id: UUID,
        *,
        error_message: str,
        provider_response: dict[str, object] | None = None,
    ) -> NotificationResponse | None:
        notification = await self.notification_repository.update_status(
            notification_id,
            status=NotificationStatus.FAILED.value,
            error_message=error_message,
            provider_response=provider_response,
            failed_at=self._utc_now(),
        )
        if notification is not None:
            logger.error(
                "Notification failed notification_id=%s error=%s",
                notification_id,
                error_message,
            )
        return self._as_response(notification)

    async def increment_attempt_count(self, notification_id: UUID) -> NotificationResponse | None:
        notification = await self.notification_repository.increment_attempt_count(notification_id)
        return self._as_response(notification)

    @staticmethod
    def _as_response(notification) -> NotificationResponse | None:
        if notification is None:
            return None
        return NotificationResponse.from_model(notification)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
