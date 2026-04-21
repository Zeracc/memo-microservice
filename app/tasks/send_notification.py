from __future__ import annotations

import logging
import random
from typing import Any
from uuid import UUID

from app.clients.uazapi_client import UazapiClient, UazapiPermanentError, UazapiRetryableError
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.celery_app import celery_app
from app.repositories.notification_repository import NotificationRepository
from app.schemas.job import JobResult
from app.services.notification_service import NotificationService
from app.tasks.base import JobAwareTask


logger = logging.getLogger(__name__)


class SendNotificationTask(JobAwareTask):
    name = "app.tasks.send_notification.send_notification_task"
    max_retries = 3

    async def run_async(self, job_service, notification_id: str, job_id: str) -> dict[str, Any]:
        notification_uuid = UUID(notification_id)
        settings = get_settings()
        logger.info(
            "Notification task started notification_id=%s job_id=%s retries=%s",
            notification_id,
            job_id,
            self.request.retries,
        )

        async with get_session_factory()() as session:
            repository = NotificationRepository(session)
            notification_service = NotificationService(repository, job_service, task_dispatcher=None)
            notification = await repository.get_by_id(notification_uuid)
            if notification is None:
                logger.warning("Notification %s was not found when Celery processing started", notification_id)
                return {"notification_id": notification_id, "status": "missing"}

            await job_service.mark_processing(job_id, message="Worker iniciou o envio da notificacao.")
            notification = await notification_service.mark_processing(notification_uuid)
            if notification is None:
                raise RuntimeError(f"Notification {notification_id} not found before processing")

            notification = await notification_service.increment_attempt_count(notification_uuid)
            if notification is None:
                raise RuntimeError(f"Notification {notification_id} not found before attempt increment")

            await job_service.update_progress(
                job_id,
                phase="sending_to_provider",
                progress_percentage=30,
                message="Enviando notificacao para a Uazapi.",
                progress_detail={"notification_id": notification_id, "attempt": notification.attempt_count},
            )

            client = UazapiClient(settings)
            try:
                delivery_result = await client.send_text_message(
                    recipient=notification.recipient,
                    message=notification.message,
                    external_id=notification.external_id,
                    metadata=notification.metadata,
                )
            except UazapiRetryableError as exc:
                logger.warning(
                    "Retryable Uazapi error notification_id=%s job_id=%s error=%s",
                    notification_id,
                    job_id,
                    exc,
                )
                return await self._handle_retryable_error(
                    job_service=job_service,
                    notification_service=notification_service,
                    notification_id=notification_uuid,
                    job_id=job_id,
                    error_message=str(exc) or exc.__class__.__name__,
                )
            except UazapiPermanentError as exc:
                await notification_service.mark_failed(
                    notification_uuid,
                    error_message=str(exc) or exc.__class__.__name__,
                )
                await job_service.mark_failed(
                    job_id,
                    {
                        "type": exc.__class__.__name__,
                        "message": str(exc) or exc.__class__.__name__,
                        "phase": "sending_to_provider",
                    },
                    message="Falha permanente ao enviar notificacao.",
                    phase="sending_to_provider",
                )
                logger.error(
                    "Permanent Uazapi error notification_id=%s job_id=%s error=%s",
                    notification_id,
                    job_id,
                    exc,
                )
                raise
            except Exception as exc:
                await notification_service.mark_failed(
                    notification_uuid,
                    error_message=str(exc) or exc.__class__.__name__,
                )
                await job_service.mark_failed(
                    job_id,
                    {
                        "type": exc.__class__.__name__,
                        "message": str(exc) or exc.__class__.__name__,
                        "phase": "sending_to_provider",
                    },
                    message="Falha inesperada ao enviar notificacao.",
                    phase="sending_to_provider",
                )
                logger.exception(
                    "Unexpected notification task error notification_id=%s job_id=%s",
                    notification_id,
                    job_id,
                )
                raise

            sent_notification = await notification_service.mark_sent(
                notification_uuid,
                provider_message_id=delivery_result.provider_message_id,
                provider_response=delivery_result.raw_response,
            )
            if sent_notification is None:
                raise RuntimeError(f"Notification {notification_id} not found after provider success")

            completed_job = await job_service.mark_completed(
                job_id,
                JobResult(
                    notification_id=sent_notification.id,
                    provider=sent_notification.provider,
                    provider_message_id=sent_notification.provider_message_id,
                    provider_status=sent_notification.status.value,
                    provider_response=sent_notification.provider_response,
                    completed_at=sent_notification.updated_at,
                ),
                message="Notificacao enviada com sucesso.",
            )

            return {
                "notification_id": str(sent_notification.id),
                "job_id": job_id,
                "status": completed_job.status.value if completed_job else "missing",
                "provider_message_id": sent_notification.provider_message_id,
            }

    async def _handle_retryable_error(
        self,
        *,
        job_service,
        notification_service: NotificationService,
        notification_id: UUID,
        job_id: str,
        error_message: str,
    ) -> dict[str, Any]:
        attempt_number = self.request.retries + 1
        max_attempts = self.max_retries + 1

        if self.request.retries >= self.max_retries:
            await notification_service.mark_failed(notification_id, error_message=error_message)
            await job_service.mark_failed(
                job_id,
                {
                    "type": "UazapiRetryableError",
                    "message": error_message,
                    "phase": "sending_to_provider",
                },
                message="Falha no envio apos esgotar as tentativas.",
                phase="sending_to_provider",
            )
            logger.error(
                "Notification retries exhausted notification_id=%s job_id=%s error=%s",
                notification_id,
                job_id,
                error_message,
            )
            raise UazapiRetryableError(error_message)

        await notification_service.mark_retrying(notification_id, error_message=error_message)
        await job_service.update_progress(
            job_id,
            phase="retrying",
            progress_percentage=15,
            message=f"Falha transitoria no provider. Reagendando tentativa {attempt_number + 1}/{max_attempts}.",
            progress_detail={
                "attempt": attempt_number,
                "max_attempts": max_attempts,
                "error_message": error_message,
            },
        )

        raise self.retry(exc=UazapiRetryableError(error_message), countdown=self._retry_countdown(attempt_number))

    @staticmethod
    def _retry_countdown(attempt_number: int) -> int:
        base_delay = min(2 ** attempt_number, 60)
        return base_delay + random.randint(0, 3)


send_notification_task = celery_app.register_task(SendNotificationTask())
