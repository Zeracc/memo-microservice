from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "memo_microservice",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.process_text", "app.tasks.send_notification"],
)

celery_app.conf.update(
    task_track_started=settings.celery_task_track_started,
    result_expires=settings.celery_result_expires,
    result_backend_transport_options={
        "global_keyprefix": settings.celery_result_keyprefix,
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=False,
)
