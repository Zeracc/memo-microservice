import logging

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError

from app.dependencies.jobs import get_job_service
from app.schemas.job import JobProcessRequest, JobQueuedResponse, JobStatusResponse
from app.services.job_service import JobService
from app.tasks.process_text import process_text_task


router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.post(
    "/process",
    response_model=JobQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_job(
    payload: JobProcessRequest,
    job_service: JobService = Depends(get_job_service),
) -> JobQueuedResponse:
    try:
        queued_job = await job_service.create_job(payload)
    except RedisError as exc:
        logger.error("Failed to create job because Redis is unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        ) from exc

    try:
        async_result = process_text_task.delay(job_id=queued_job.job_id)
    except Exception as exc:
        logger.exception("Failed to enqueue Celery task for job %s", queued_job.job_id)
        await job_service.mark_failed(queued_job.job_id, f"Failed to enqueue task: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue unavailable",
        ) from exc

    logger.info("Job enqueued: %s (celery_task_id=%s)", queued_job.job_id, async_result.id)
    return queued_job


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_job(
    job_id: str,
    job_service: JobService = Depends(get_job_service),
) -> JobStatusResponse:
    try:
        job = await job_service.get_job(job_id)
    except RedisError as exc:
        logger.error("Failed to read job %s because Redis is unavailable: %s", job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        ) from exc

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job
