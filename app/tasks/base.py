import asyncio
from abc import ABC, abstractmethod
from typing import Any

from celery import Task
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import dispose_database
from app.dependencies.redis import get_redis_client_for_worker
from app.services.job_service import JobService
from app.services.redis_service import RedisService


class JobAwareTask(Task, ABC):
    abstract = True

    def _build_redis_client(self) -> Redis:
        return get_redis_client_for_worker()

    def _build_job_service(self, redis: Redis) -> JobService:
        settings = get_settings()
        return JobService(RedisService(redis, job_ttl_seconds=settings.job_ttl_seconds))

    @abstractmethod
    async def run_async(self, job_service: JobService, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def run(self, *args: Any, **kwargs: Any) -> Any:
        return asyncio.run(self._run_with_job_service(*args, **kwargs))

    async def _run_with_job_service(self, *args: Any, **kwargs: Any) -> Any:
        redis = self._build_redis_client()
        try:
            job_service = self._build_job_service(redis)
            return await self.run_async(job_service, *args, **kwargs)
        finally:
            await redis.aclose()
            await dispose_database()
