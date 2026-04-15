import unittest
from datetime import datetime, timezone

from app.domain.job_status import JobStatus
from app.schemas.job import JobInput, JobResult, JobStatusResponse
from app.services.redis_service import RedisService
from tests.helpers import FakeRedis


class RedisServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()
        self.service = RedisService(self.redis, job_ttl_seconds=3600)
        now = datetime.now(timezone.utc)
        self.job = JobStatusResponse(
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

    async def test_set_job_saves_with_ttl(self) -> None:
        await self.service.set_job(self.job.job_id, self.job)

        self.assertEqual(self.redis.expirations["job:job-123"], 3600)

    async def test_get_job_returns_schema(self) -> None:
        await self.service.set_job(self.job.job_id, self.job)

        stored_job = await self.service.get_job(self.job.job_id)

        self.assertIsNotNone(stored_job)
        self.assertEqual(stored_job.job_id, self.job.job_id)
        self.assertEqual(stored_job.status, JobStatus.QUEUED)

    async def test_get_job_returns_none_when_missing(self) -> None:
        stored_job = await self.service.get_job("missing")

        self.assertIsNone(stored_job)

    async def test_update_job_reapplies_ttl(self) -> None:
        await self.service.set_job(self.job.job_id, self.job)

        updated_job = await self.service.update_job(
            self.job.job_id,
            {
                "status": JobStatus.COMPLETED,
                "result": JobResult(
                    processed_text="HELLO",
                    document_id="doc-1",
                    summary="Resumo",
                    keywords=["hello"],
                    recommendation_count=1,
                    completed_at=datetime.now(timezone.utc),
                ),
                "updated_at": datetime.now(timezone.utc),
            },
        )

        self.assertIsNotNone(updated_job)
        self.assertEqual(len(list(self.redis.values_for_key("job:job-123"))), 2)
        self.assertEqual(self.redis.set_calls[-1]["ex"], 3600)

    async def test_update_job_ignores_unknown_fields(self) -> None:
        await self.service.set_job(self.job.job_id, self.job)

        updated_job = await self.service.update_job(
            self.job.job_id,
            {
                "status": JobStatus.PROCESSING,
                "unexpected": "value",
                "updated_at": datetime.now(timezone.utc),
            },
        )

        self.assertIsNotNone(updated_job)
        self.assertFalse(hasattr(updated_job, "unexpected"))
        self.assertEqual(updated_job.status, JobStatus.PROCESSING)

    async def test_get_job_returns_none_for_invalid_payload(self) -> None:
        self.redis.store["job:broken"] = "{not-json"

        stored_job = await self.service.get_job("broken")

        self.assertIsNone(stored_job)
