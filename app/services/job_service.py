import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.domain.job_status import JobStatus
from app.schemas.job import (
    JobErrorDetail,
    JobInput,
    JobProcessRequest,
    JobProgressEvent,
    JobQueuedResponse,
    JobResult,
    JobStatusResponse,
)
from app.services.redis_service import RedisService


logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, redis_service: RedisService) -> None:
        self.redis_service = redis_service

    async def create_job(self, payload: JobProcessRequest) -> JobQueuedResponse:
        now = self._utc_now()
        queued_event = self._build_progress_event(
            phase="queued",
            progress_percentage=0,
            message="Job enfileirado com sucesso.",
            progress_detail=None,
            status=JobStatus.QUEUED,
            recorded_at=now,
        )
        job_id = str(uuid4())
        job = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            input=JobInput(text=payload.text),
            message=queued_event.message,
            result=None,
            error=None,
            phase=queued_event.phase,
            progress_percentage=queued_event.progress_percentage,
            progress_detail=queued_event.progress_detail,
            progress_history=[queued_event],
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

    async def mark_processing(
        self,
        job_id: str,
        *,
        message: str | None = None,
    ) -> JobStatusResponse | None:
        job = await self._update_job(
            job_id,
            status=JobStatus.PROCESSING,
            phase="processing",
            progress_percentage=None,
            message=message,
            progress_detail=None,
            error=None,
        )
        if job is not None:
            logger.info("Job processing started: %s", job_id)
        return job

    async def update_progress(
        self,
        job_id: str,
        *,
        phase: str,
        progress_percentage: int,
        message: str | None = None,
        progress_detail: dict[str, Any] | None = None,
    ) -> JobStatusResponse | None:
        job = await self._update_job(
            job_id,
            status=JobStatus.PROCESSING,
            phase=phase,
            progress_percentage=progress_percentage,
            message=message,
            progress_detail=progress_detail,
            error=None,
        )
        if job is not None:
            logger.info(
                "Job progress updated: %s phase=%s progress=%s",
                job_id,
                phase,
                progress_percentage,
            )
        return job

    async def mark_completed(
        self,
        job_id: str,
        result: JobResult,
        *,
        message: str | None = None,
    ) -> JobStatusResponse | None:
        job = await self._update_job(
            job_id,
            status=JobStatus.COMPLETED,
            phase="completed",
            progress_percentage=100,
            message=message or "Processamento concluido com sucesso.",
            progress_detail=None,
            error=None,
            result=result,
        )
        if job is not None:
            logger.info("Job completed: %s", job_id)
        return job

    async def mark_failed(
        self,
        job_id: str,
        error: str | dict[str, Any] | JobErrorDetail,
        *,
        message: str | None = None,
        phase: str | None = None,
    ) -> JobStatusResponse | None:
        error_payload = self._normalize_error(error=error, phase=phase)
        job = await self._update_job(
            job_id,
            status=JobStatus.FAILED,
            phase=phase or error_payload.phase or "failed",
            progress_percentage=None,
            message=message or "Falha no processamento do job.",
            progress_detail=None,
            error=error_payload,
        )
        if job is not None:
            logger.error("Job failed: %s", job_id)
        return job

    async def _update_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        phase: str | None,
        progress_percentage: int | None,
        message: str | None,
        progress_detail: dict[str, Any] | None,
        error: str | JobErrorDetail | None,
        result: JobResult | None = None,
    ) -> JobStatusResponse | None:
        current_job = await self.redis_service.get_job(job_id)
        if current_job is None:
            return None

        now = self._utc_now()
        history = list(current_job.progress_history)
        if phase is not None:
            history.append(
                self._build_progress_event(
                    phase=phase,
                    progress_percentage=progress_percentage,
                    message=message,
                    progress_detail=progress_detail,
                    status=status,
                    recorded_at=now,
                )
            )

        return await self.redis_service.update_job(
            job_id,
            {
                "status": status,
                "phase": phase,
                "progress_percentage": progress_percentage,
                "message": message,
                "progress_detail": progress_detail,
                "progress_history": history,
                "error": error,
                "result": result if result is not None else current_job.result,
                "updated_at": now,
            },
        )

    @staticmethod
    def _build_progress_event(
        *,
        phase: str,
        progress_percentage: int | None,
        message: str | None,
        progress_detail: dict[str, Any] | None,
        status: JobStatus,
        recorded_at: datetime,
    ) -> JobProgressEvent:
        return JobProgressEvent(
            phase=phase,
            progress_percentage=progress_percentage if progress_percentage is not None else 0,
            message=message,
            progress_detail=progress_detail,
            status=status,
            recorded_at=recorded_at,
        )

    @staticmethod
    def _normalize_error(
        *,
        error: str | dict[str, Any] | JobErrorDetail,
        phase: str | None,
    ) -> str | JobErrorDetail:
        if isinstance(error, JobErrorDetail):
            return error.model_copy(update={"phase": phase or error.phase})
        if isinstance(error, dict):
            return JobErrorDetail(
                type=str(error.get("type", "JobError")),
                message=str(error.get("message", "Unknown error")),
                phase=phase or (str(error["phase"]) if error.get("phase") else None),
            )
        return JobErrorDetail(
            type="JobError",
            message=error,
            phase=phase,
        )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
