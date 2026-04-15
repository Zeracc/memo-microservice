import logging
from typing import Any

from app.core.celery_app import celery_app
from app.services.job_service import JobService
from app.services.pipeline_service import TextPipelineService
from app.tasks.base import JobAwareTask


logger = logging.getLogger(__name__)
RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)


class ProcessTextTask(JobAwareTask):
    name = "app.tasks.process_text.process_text_task"
    autoretry_for = RETRYABLE_EXCEPTIONS
    retry_backoff = True
    retry_jitter = True
    max_retries = 3

    async def run_async(self, job_service: JobService, job_id: str) -> dict[str, Any]:
        job = await job_service.get_job(job_id)
        if job is None:
            logger.warning("Job %s was not found when Celery processing started", job_id)
            return {"job_id": job_id, "status": "missing"}

        pipeline = TextPipelineService()
        current_phase = job.phase or "queued"

        try:
            await self._report_progress(
                job_service,
                job_id,
                phase="loading_input",
                progress_percentage=5,
                message="Carregando e normalizando o texto.",
            )
            current_phase = "loading_input"
            document = await pipeline.load_input(job.input.text)

            await self._report_progress(
                job_service,
                job_id,
                phase="extracting_metadata",
                progress_percentage=20,
                message="Extraindo metadados do texto.",
                progress_detail={"document_id": document.document_id},
            )
            current_phase = "extracting_metadata"
            metadata = await pipeline.extract_metadata(document)

            await self._report_progress(
                job_service,
                job_id,
                phase="analyzing_content",
                progress_percentage=55,
                message="Analisando estrutura e topicos principais.",
                progress_detail=metadata,
            )
            current_phase = "analyzing_content"
            analysis = await pipeline.analyze_content(document, metadata)

            await self._report_progress(
                job_service,
                job_id,
                phase="generating_recommendations",
                progress_percentage=80,
                message="Gerando recomendacoes a partir da analise.",
                progress_detail={"keywords": analysis["keywords"]},
            )
            current_phase = "generating_recommendations"
            recommendations = await pipeline.generate_recommendations(metadata, analysis)

            await self._report_progress(
                job_service,
                job_id,
                phase="finalizing",
                progress_percentage=95,
                message="Consolidando resultado final do pipeline.",
                progress_detail={"recommendation_count": len(recommendations)},
            )
            current_phase = "finalizing"
            result = await pipeline.build_result(document, metadata, analysis, recommendations)

            completed_job = await job_service.mark_completed(
                job_id,
                result,
                message="Processamento concluido com sucesso.",
            )
            if completed_job is None:
                logger.warning("Job %s disappeared before completion could be persisted", job_id)
                return {"job_id": job_id, "status": "missing"}

            return {
                "job_id": job_id,
                "status": completed_job.status.value,
                "result": completed_job.result.model_dump() if completed_job.result else None,
            }
        except RETRYABLE_EXCEPTIONS:
            logger.warning("Retryable error while processing job %s", job_id, exc_info=True)
            raise
        except Exception as exc:
            await job_service.mark_failed(
                job_id,
                {
                    "type": exc.__class__.__name__,
                    "message": str(exc) or exc.__class__.__name__,
                    "phase": current_phase,
                },
                message="Falha no processamento do pipeline.",
                phase=current_phase,
            )
            raise

    async def _report_progress(
        self,
        job_service: JobService,
        job_id: str,
        *,
        phase: str,
        progress_percentage: int,
        message: str,
        progress_detail: dict[str, Any] | None = None,
    ) -> None:
        updated_job = await job_service.update_progress(
            job_id,
            phase=phase,
            progress_percentage=progress_percentage,
            message=message,
            progress_detail=progress_detail,
        )
        if updated_job is None:
            raise RuntimeError(f"Job {job_id} not found while updating progress")

        self.update_state(
            state="PROGRESS",
            meta={
                "job_id": job_id,
                "phase": phase,
                "progress": progress_percentage,
            },
        )


process_text_task = celery_app.register_task(ProcessTextTask())
