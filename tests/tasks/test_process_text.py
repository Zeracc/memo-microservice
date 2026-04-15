import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.job_status import JobStatus
from app.schemas.job import JobInput, JobProgressEvent, JobResult, JobStatusResponse
from app.tasks.process_text import process_text_task


class StubJobService:
    def __init__(self, job: JobStatusResponse) -> None:
        self.job = job
        self.progress_updates: list[dict[str, object]] = []
        self.completed_calls: list[tuple[str, JobResult, str | None]] = []
        self.failed_calls: list[tuple[str, object, str | None, str | None]] = []

    async def get_job(self, job_id: str) -> JobStatusResponse | None:
        return self.job

    async def update_progress(
        self,
        job_id: str,
        *,
        phase: str,
        progress_percentage: int,
        message: str | None = None,
        progress_detail: dict[str, object] | None = None,
    ) -> JobStatusResponse | None:
        self.progress_updates.append(
            {
                "job_id": job_id,
                "phase": phase,
                "progress_percentage": progress_percentage,
                "message": message,
                "progress_detail": progress_detail,
            }
        )
        self.job = self.job.model_copy(
            update={
                "status": JobStatus.PROCESSING,
                "phase": phase,
                "progress_percentage": progress_percentage,
                "message": message,
                "progress_detail": progress_detail,
                "progress_history": [
                    *self.job.progress_history,
                    JobProgressEvent(
                        phase=phase,
                        progress_percentage=progress_percentage,
                        message=message,
                        progress_detail=progress_detail,
                        status=JobStatus.PROCESSING,
                        recorded_at=datetime.now(timezone.utc),
                    ),
                ],
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return self.job

    async def mark_completed(
        self,
        job_id: str,
        result: JobResult,
        *,
        message: str | None = None,
    ) -> JobStatusResponse | None:
        self.completed_calls.append((job_id, result, message))
        self.job = self.job.model_copy(
            update={
                "status": JobStatus.COMPLETED,
                "phase": "completed",
                "progress_percentage": 100,
                "result": result,
                "message": message,
                "progress_history": [
                    *self.job.progress_history,
                    JobProgressEvent(
                        phase="completed",
                        progress_percentage=100,
                        message=message,
                        progress_detail=None,
                        status=JobStatus.COMPLETED,
                        recorded_at=datetime.now(timezone.utc),
                    ),
                ],
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return self.job

    async def mark_failed(
        self,
        job_id: str,
        error: object,
        *,
        message: str | None = None,
        phase: str | None = None,
    ) -> JobStatusResponse | None:
        self.failed_calls.append((job_id, error, message, phase))
        self.job = self.job.model_copy(
            update={
                "status": JobStatus.FAILED,
                "phase": phase,
                "error": error,
                "message": message,
                "progress_history": [
                    *self.job.progress_history,
                    JobProgressEvent(
                        phase=phase or "failed",
                        progress_percentage=self.job.progress_percentage or 0,
                        message=message,
                        progress_detail=None,
                        status=JobStatus.FAILED,
                        recorded_at=datetime.now(timezone.utc),
                    ),
                ],
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return self.job


class ProcessTextTaskTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        now = datetime.now(timezone.utc)
        self.job = JobStatusResponse(
            job_id="job-123",
            status=JobStatus.QUEUED,
            input=JobInput(text="hello world from celery"),
            message="Job enfileirado com sucesso.",
            result=None,
            error=None,
            phase="queued",
            progress_percentage=0,
            progress_detail=None,
            progress_history=[
                JobProgressEvent(
                    phase="queued",
                    progress_percentage=0,
                    message="Job enfileirado com sucesso.",
                    progress_detail=None,
                    status=JobStatus.QUEUED,
                    recorded_at=now,
                )
            ],
            created_at=now,
            updated_at=now,
        )
        self.service = StubJobService(self.job)
        self.original_update_state = process_text_task.update_state
        process_text_task.update_state = MagicMock()

    def tearDown(self) -> None:
        process_text_task.update_state = self.original_update_state

    async def test_task_reports_all_pipeline_phases_and_completes(self) -> None:
        result = await process_text_task.run_async(self.service, "job-123")

        phases = [entry["phase"] for entry in self.service.progress_updates]
        self.assertEqual(
            phases,
            [
                "loading_input",
                "extracting_metadata",
                "analyzing_content",
                "generating_recommendations",
                "finalizing",
            ],
        )
        self.assertEqual(self.service.completed_calls[0][0], "job-123")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"]["recommendation_count"], 2)
        self.assertEqual(self.service.job.progress_history[-1].phase, "completed")

    async def test_task_marks_failed_with_phase_information(self) -> None:
        with patch(
            "app.tasks.process_text.TextPipelineService.analyze_content",
            new=AsyncMock(side_effect=RuntimeError("analysis exploded")),
        ):
            with self.assertRaises(RuntimeError):
                await process_text_task.run_async(self.service, "job-123")

        self.assertEqual(len(self.service.failed_calls), 1)
        _, error, message, phase = self.service.failed_calls[0]
        self.assertEqual(message, "Falha no processamento do pipeline.")
        self.assertEqual(phase, "analyzing_content")
        self.assertEqual(error["phase"], "analyzing_content")
        self.assertEqual(self.service.job.progress_history[-1].phase, "analyzing_content")
