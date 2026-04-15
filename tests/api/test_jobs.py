import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.dependencies.jobs import get_job_service
from app.domain.job_status import JobStatus
from app.main import app
from app.schemas.job import JobInput, JobProcessRequest, JobQueuedResponse, JobStatusResponse


class StubJobService:
    def __init__(
        self,
        job: JobStatusResponse | None,
        queued_job: JobQueuedResponse | None = None,
    ) -> None:
        self.job = job
        self.queued_job = queued_job
        self.failed_jobs: list[tuple[str, str]] = []

    async def create_job(self, payload: JobProcessRequest) -> JobQueuedResponse:
        if self.queued_job is None:
            raise AssertionError("queued_job was not configured for this test")
        return self.queued_job

    async def get_job(self, job_id: str) -> JobStatusResponse | None:
        return self.job

    async def mark_failed(self, job_id: str, error_message: str) -> JobStatusResponse | None:
        self.failed_jobs.append((job_id, error_message))
        return self.job


class JobRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_get_job_returns_404_for_missing_job(self) -> None:
        app.dependency_overrides[get_job_service] = lambda: StubJobService(None)

        response = self.client.get("/jobs/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Job not found"})

    def test_get_job_returns_200_for_existing_job(self) -> None:
        now = datetime.now(timezone.utc)
        job = JobStatusResponse(
            job_id="job-123",
            status=JobStatus.QUEUED,
            input=JobInput(text="hello"),
            message="Job enfileirado com sucesso.",
            result=None,
            error=None,
            phase="queued",
            progress_percentage=0,
            progress_detail=None,
            created_at=now,
            updated_at=now,
        )
        app.dependency_overrides[get_job_service] = lambda: StubJobService(job)

        response = self.client.get("/jobs/job-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "job-123")
        self.assertEqual(response.json()["status"], "queued")

    def test_create_job_returns_202_and_enqueues_celery_task(self) -> None:
        stub_service = StubJobService(
            job=None,
            queued_job=JobQueuedResponse(job_id="job-123", status=JobStatus.QUEUED),
        )
        app.dependency_overrides[get_job_service] = lambda: stub_service

        with patch("app.api.jobs.process_text_task.delay") as delay_mock:
            delay_mock.return_value.id = "celery-123"

            response = self.client.post("/jobs/process", json={"text": "hello"})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_id": "job-123", "status": "queued"})
        delay_mock.assert_called_once_with(job_id="job-123")
