from typing import Any

from fastapi.encoders import jsonable_encoder
from redis.asyncio import Redis

from app.schemas.job import JobStatusResponse


class RedisService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"job:{job_id}"

    async def set_job(self, job_id: str, job_data: JobStatusResponse) -> None:
        await self.redis.set(self._job_key(job_id), job_data.model_dump_json())

    async def get_job(self, job_id: str) -> JobStatusResponse | None:
        payload = await self.redis.get(self._job_key(job_id))
        if payload is None:
            return None

        return JobStatusResponse.model_validate_json(payload)

    async def update_job(
        self,
        job_id: str,
        fields_to_update: dict[str, Any],
    ) -> JobStatusResponse | None:
        current_job = await self.get_job(job_id)
        if current_job is None:
            return None

        updated_payload = current_job.model_dump(mode="json")
        updated_payload.update(jsonable_encoder(fields_to_update))

        updated_job = JobStatusResponse.model_validate(updated_payload)
        await self.set_job(job_id, updated_job)
        return updated_job
