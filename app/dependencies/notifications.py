from collections.abc import Callable
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies.jobs import get_job_service
from app.repositories.notification_repository import NotificationRepository
from app.services.job_service import JobService
from app.services.notification_service import NotificationService
from app.tasks.send_notification import send_notification_task


def _dispatch_notification(notification_id: UUID, job_id: UUID) -> str | None:
    async_result = send_notification_task.delay(
        notification_id=str(notification_id),
        job_id=str(job_id),
    )
    return async_result.id


def get_notification_repository(
    session: AsyncSession = Depends(get_db_session),
) -> NotificationRepository:
    return NotificationRepository(session)


def get_notification_dispatcher() -> Callable[[UUID, UUID], str | None]:
    return _dispatch_notification


def get_notification_service(
    notification_repository: NotificationRepository = Depends(get_notification_repository),
    job_service: JobService = Depends(get_job_service),
    task_dispatcher: Callable[[UUID, UUID], str | None] = Depends(get_notification_dispatcher),
) -> NotificationService:
    return NotificationService(notification_repository, job_service, task_dispatcher)
