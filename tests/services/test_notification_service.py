import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.domain.notification_status import NotificationStatus
from app.schemas.notification import NotificationCreateRequest
from app.services.notification_service import NotificationService


class FakeNotificationRepository:
    def __init__(self, existing=None) -> None:
        self.session = SimpleNamespace(rollback=self._rollback)
        self.rollback_called = False
        self.existing = existing
        self.created = None
        self.created_payload = None
        self.last_job_id = None

    async def _rollback(self) -> None:
        self.rollback_called = True

    async def get_by_external_id(self, external_id: str):
        return self.existing

    async def create(self, **kwargs):
        self.created_payload = kwargs
        self.created = SimpleNamespace(
            id=uuid4(),
            external_id=kwargs["external_id"],
            recipient=kwargs["recipient"],
            message=kwargs["message"],
            priority=kwargs["priority"],
            provider="uazapi",
            notification_type="whatsapp",
            status=kwargs["status"],
            last_job_id=None,
        )
        return self.created

    async def set_job_id(self, notification_id, job_id):
        if self.created is None:
            return None
        self.created.last_job_id = job_id
        return self.created

    async def update_status(self, *args, **kwargs):
        notification = self.created or self.existing
        if notification is None:
            return None
        notification.status = kwargs["status"]
        notification.error_message = kwargs.get("error_message")
        return notification

    async def get_by_id(self, notification_id):
        return self.created or self.existing

    async def list(self, filters):
        return [], 0

    async def increment_attempt_count(self, notification_id):
        return self.created or self.existing


class FakeJobService:
    def __init__(self) -> None:
        self.created_inputs = []
        self.failed = []

    async def create_tracking_job(self, job_input, *, message: str):
        self.created_inputs.append((job_input, message))
        return SimpleNamespace(job_id=uuid4())

    async def mark_failed(self, job_id, error, *, message=None, phase=None):
        self.failed.append((job_id, error, message, phase))
        return None


class NotificationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_notification_reuses_existing_external_id(self) -> None:
        existing = SimpleNamespace(
            id=uuid4(),
            external_id="pedido-123",
            recipient="5531999999999",
            message="Seu pedido foi aprovado",
            priority="normal",
            provider="uazapi",
            notification_type="whatsapp",
            status=NotificationStatus.SENT.value,
            last_job_id=uuid4(),
        )
        repository = FakeNotificationRepository(existing=existing)
        job_service = FakeJobService()
        dispatcher_calls = []
        service = NotificationService(
            repository,
            job_service,
            task_dispatcher=lambda notification_id, job_id: dispatcher_calls.append((notification_id, job_id)),
        )

        response = await service.create_notification(
            NotificationCreateRequest(
                external_id="pedido-123",
                recipient="5531999999999",
                message="Seu pedido foi aprovado",
            )
        )

        self.assertTrue(response.already_exists)
        self.assertEqual(response.notification_id, existing.id)
        self.assertEqual(response.job_id, existing.last_job_id)
        self.assertEqual(response.status, NotificationStatus.SENT)
        self.assertEqual(job_service.created_inputs, [])
        self.assertEqual(dispatcher_calls, [])

    async def test_create_notification_persists_and_enqueues_job(self) -> None:
        repository = FakeNotificationRepository()
        job_service = FakeJobService()
        dispatched = []

        def dispatcher(notification_id, job_id):
            dispatched.append((notification_id, job_id))
            return "celery-123"

        service = NotificationService(repository, job_service, task_dispatcher=dispatcher)

        response = await service.create_notification(
            NotificationCreateRequest(
                external_id="pedido-123",
                recipient="5531999999999",
                message="Seu pedido foi aprovado",
                priority="high",
                metadata={"order_id": 123},
            )
        )

        self.assertFalse(response.already_exists)
        self.assertEqual(response.status, NotificationStatus.PENDING)
        self.assertEqual(repository.created_payload["priority"], "high")
        self.assertEqual(repository.created_payload["metadata"], {"order_id": 123})
        self.assertEqual(len(job_service.created_inputs), 1)
        self.assertEqual(len(dispatched), 1)
