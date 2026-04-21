import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.dependencies.notifications import get_notification_service
from app.domain.notification_status import NotificationStatus
from app.main import app
from app.repositories.notification_repository import NotificationListFilters
from app.schemas.notification import (
    NotificationCreateRequest,
    NotificationCreateResponse,
    NotificationListResponse,
    NotificationResponse,
)


class StubNotificationService:
    def __init__(
        self,
        *,
        created: NotificationCreateResponse | None = None,
        notification: NotificationResponse | None = None,
        listing: NotificationListResponse | None = None,
    ) -> None:
        self.created = created
        self.notification = notification
        self.listing = listing
        self.create_payloads: list[NotificationCreateRequest] = []
        self.list_filters: list[NotificationListFilters] = []

    async def create_notification(self, payload: NotificationCreateRequest) -> NotificationCreateResponse:
        self.create_payloads.append(payload)
        if self.created is None:
            raise AssertionError("created response was not configured for this test")
        return self.created

    async def get_notification(self, notification_id):
        return self.notification

    async def list_notifications(self, filters: NotificationListFilters) -> NotificationListResponse:
        self.list_filters.append(filters)
        if self.listing is None:
            raise AssertionError("listing response was not configured for this test")
        return self.listing


class NotificationRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_create_notification_returns_202(self) -> None:
        notification_id = uuid4()
        job_id = uuid4()
        stub_service = StubNotificationService(
            created=NotificationCreateResponse(
                notification_id=notification_id,
                job_id=job_id,
                status=NotificationStatus.PENDING,
                already_exists=False,
            )
        )
        app.dependency_overrides[get_notification_service] = lambda: stub_service

        response = self.client.post(
            "/notifications",
            json={
                "external_id": "pedido-123",
                "recipient": "5531999999999",
                "message": "Seu pedido foi aprovado",
                "priority": "normal",
                "metadata": {"order_id": 123},
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["notification_id"], str(notification_id))
        self.assertEqual(response.json()["job_id"], str(job_id))
        self.assertEqual(response.json()["status"], "pending")

    def test_get_notification_returns_404_for_missing_notification(self) -> None:
        app.dependency_overrides[get_notification_service] = lambda: StubNotificationService(notification=None)

        response = self.client.get(f"/notifications/{uuid4()}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Notification not found"})

    def test_get_notification_returns_notification_payload(self) -> None:
        now = datetime.now(timezone.utc)
        notification_id = uuid4()
        job_id = uuid4()
        stub_service = StubNotificationService(
            notification=NotificationResponse(
                id=notification_id,
                external_id="pedido-123",
                recipient="5531999999999",
                message="Seu pedido foi aprovado",
                type="whatsapp",
                priority="normal",
                status=NotificationStatus.SENT,
                provider="uazapi",
                provider_message_id="msg-123",
                provider_response={"status": "success"},
                error_message=None,
                metadata={"order_id": 123},
                attempt_count=1,
                job_id=job_id,
                created_at=now,
                updated_at=now,
                sent_at=now,
                failed_at=None,
            )
        )
        app.dependency_overrides[get_notification_service] = lambda: stub_service

        response = self.client.get(f"/notifications/{notification_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(notification_id))
        self.assertEqual(response.json()["status"], "sent")
        self.assertEqual(response.json()["job_id"], str(job_id))

    def test_list_notifications_returns_paginated_payload(self) -> None:
        now = datetime.now(timezone.utc)
        notification_id = uuid4()
        stub_service = StubNotificationService(
            listing=NotificationListResponse(
                items=[
                    NotificationResponse(
                        id=notification_id,
                        external_id="pedido-123",
                        recipient="5531999999999",
                        message="Seu pedido foi aprovado",
                        type="whatsapp",
                        priority="normal",
                        status=NotificationStatus.PENDING,
                        provider="uazapi",
                        provider_message_id=None,
                        provider_response=None,
                        error_message=None,
                        metadata={"order_id": 123},
                        attempt_count=0,
                        job_id=uuid4(),
                        created_at=now,
                        updated_at=now,
                        sent_at=None,
                        failed_at=None,
                    )
                ],
                page=2,
                limit=10,
                total=21,
            )
        )
        app.dependency_overrides[get_notification_service] = lambda: stub_service

        response = self.client.get("/notifications?page=2&limit=10&status=pending")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page"], 2)
        self.assertEqual(response.json()["limit"], 10)
        self.assertEqual(response.json()["total"], 21)
        self.assertEqual(response.json()["items"][0]["status"], "pending")
