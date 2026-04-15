import unittest
from datetime import datetime, timezone

from app.domain.job_status import JobStatus
from app.schemas.job import JobErrorDetail, JobInput, JobProcessRequest, JobResult, JobStatusResponse
from app.services.job_service import JobService
from app.services.redis_service import RedisService
from tests.helpers import FakeRedis


class JobServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()
        self.redis_service = RedisService(self.redis, job_ttl_seconds=3600)
        self.service = JobService(self.redis_service)

    async def test_create_job_creates_with_queued_status(self) -> None:
        created = await self.service.create_job(JobProcessRequest(text="hello"))
        stored_job = await self.service.get_job(created.job_id)

        self.assertEqual(created.status, JobStatus.QUEUED)
        self.assertIsNotNone(stored_job)
        self.assertEqual(stored_job.status, JobStatus.QUEUED)
        self.assertEqual(stored_job.input.text, "hello")
        self.assertEqual(stored_job.phase, "queued")
        self.assertEqual(stored_job.progress_percentage, 0)
        self.assertEqual(len(stored_job.progress_history), 1)
        self.assertEqual(stored_job.progress_history[0].phase, "queued")

    async def test_mark_processing_updates_status(self) -> None:
        job = await self._seed_job()

        updated = await self.service.mark_processing(job.job_id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, JobStatus.PROCESSING)

    async def test_mark_completed_saves_result(self) -> None:
        job = await self._seed_job()

        updated = await self.service.mark_completed(
            job.job_id,
            JobResult(
                processed_text="HELLO",
                document_id="doc-1",
                summary="Resumo",
                keywords=["hello"],
                recommendation_count=1,
                completed_at=datetime.now(timezone.utc),
            ),
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, JobStatus.COMPLETED)
        self.assertIsNotNone(updated.result)
        self.assertEqual(updated.result.processed_text, "HELLO")
        self.assertEqual(updated.phase, "completed")
        self.assertEqual(updated.progress_percentage, 100)

    async def test_mark_failed_saves_error(self) -> None:
        job = await self._seed_job()

        updated = await self.service.mark_failed(
            job.job_id,
            {"type": "RuntimeError", "message": "boom", "phase": "analyzing_content"},
            message="Falha.",
            phase="analyzing_content",
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, JobStatus.FAILED)
        self.assertIsInstance(updated.error, JobErrorDetail)
        self.assertEqual(updated.error.message, "boom")
        self.assertEqual(updated.error.phase, "analyzing_content")

    async def test_updated_at_changes_after_update(self) -> None:
        job = await self._seed_job()

        updated = await self.service.mark_processing(job.job_id)

        self.assertIsNotNone(updated)
        self.assertGreater(updated.updated_at, job.updated_at)

    async def test_update_progress_updates_phase_percentage_and_ttl(self) -> None:
        job = await self._seed_job()
        set_calls_before = len(self.redis.set_calls)

        updated = await self.service.update_progress(
            job.job_id,
            phase="analyzing_content",
            progress_percentage=70,
            message="Analisando o texto.",
            progress_detail={"keyword_count": 4},
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, JobStatus.PROCESSING)
        self.assertEqual(updated.phase, "analyzing_content")
        self.assertEqual(updated.progress_percentage, 70)
        self.assertEqual(updated.progress_detail, {"keyword_count": 4})
        self.assertEqual(len(self.redis.set_calls), set_calls_before + 1)
        self.assertEqual(self.redis.set_calls[-1]["ex"], 3600)
        self.assertEqual(updated.progress_history[-1].phase, "analyzing_content")
        self.assertEqual(updated.progress_history[-1].progress_percentage, 70)

    async def _seed_job(self) -> JobStatusResponse:
        now = datetime.now(timezone.utc)
        job = JobStatusResponse(
            job_id="seed-job",
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
        await self.redis_service.set_job(job.job_id, job)
        return job
