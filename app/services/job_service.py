import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.job import (
    JobInput,
    JobProcessRequest,
    JobQueuedResponse,
    JobResult,
    JobStatus,
    JobStatusResponse,
)
from app.services.redis_service import RedisService


logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, redis_service: RedisService) -> None:
        self.redis_service = redis_service

    async def create_job(self, payload: JobProcessRequest) -> JobQueuedResponse:
        now = self._utc_now()
        job_id = str(uuid4())
        job = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            input=JobInput(text=payload.text),
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        )

        await self.redis_service.set_job(job_id, job)
        logger.info("Job created: %s", job_id)

        return JobQueuedResponse(job_id=job_id, status=JobStatus.QUEUED)

    async def get_job(self, job_id: str) -> JobStatusResponse | None:
        job = await self.redis_service.get_job(job_id)
        logger.info("Job fetched: %s (%s)", job_id, "found" if job else "not found")
        return job

    async def process_job(self, job_id: str) -> None:
        job = await self.redis_service.get_job(job_id)
        if job is None:
            logger.warning("Job %s was not found when background processing started", job_id)
            return

        processing_job = await self.redis_service.update_job(
            job_id,
            {
                "status": JobStatus.PROCESSING,
                "updated_at": self._utc_now(),
                "error": None,
            },
        )
        if processing_job is None:
            logger.warning("Job %s disappeared before it could move to processing", job_id)
            return

        logger.info("Job processing started: %s", job_id)

        try:
            await asyncio.sleep(3)

            result = JobResult(processed_text=processing_job.input.text.upper())
            await self.redis_service.update_job(
                job_id,
                {
                    "status": JobStatus.COMPLETED,
                    "result": result,
                    "error": None,
                    "updated_at": self._utc_now(),
                },
            )
            logger.info("Job completed: %s", job_id)
        except Exception as exc:
            error_message = str(exc) or exc.__class__.__name__
            try:
                await self._mark_job_failed(job_id, error_message)
            except Exception:
                logger.exception("Failed to persist failed status for job %s", job_id)
            logger.exception("Job failed: %s", job_id)

    async def _mark_job_failed(self, job_id: str, error_message: str) -> None:
        await self.redis_service.update_job(
            job_id,
            {
                "status": JobStatus.FAILED,
                "error": error_message,
                "updated_at": self._utc_now(),
            },
        )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
