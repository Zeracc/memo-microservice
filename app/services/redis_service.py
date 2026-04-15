import logging
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from redis.asyncio import Redis

from app.schemas.job import JobStatusResponse


logger = logging.getLogger(__name__)


class RedisService:
    allowed_update_fields = frozenset(JobStatusResponse.model_fields.keys())

    def __init__(self, redis: Redis, job_ttl_seconds: int) -> None:
        self.redis = redis
        self.job_ttl_seconds = job_ttl_seconds

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"job:{job_id}"

    async def set_job(self, job_id: str, job_data: JobStatusResponse) -> None:
        await self.redis.set(
            self._job_key(job_id),
            job_data.model_dump_json(),
            ex=self.job_ttl_seconds,
        )

    async def get_job(self, job_id: str) -> JobStatusResponse | None:
        payload = await self.redis.get(self._job_key(job_id))
        if payload is None:
            return None
        try:
            return JobStatusResponse.model_validate_json(payload)
        except ValidationError:
            logger.warning("Stored job %s has invalid payload and could not be parsed", job_id)
            return None

    async def update_job(
        self,
        job_id: str,
        fields_to_update: dict[str, Any],
    ) -> JobStatusResponse | None:
        current_job = await self.get_job(job_id)
        if current_job is None:
            return None

        updated_payload = current_job.model_dump(mode="json")
        safe_updates = {
            key: value
            for key, value in jsonable_encoder(fields_to_update).items()
            if key in self.allowed_update_fields
        }
        updated_payload.update(safe_updates)

        updated_job = JobStatusResponse.model_validate(updated_payload)
        await self.set_job(job_id, updated_job)
        return updated_job
