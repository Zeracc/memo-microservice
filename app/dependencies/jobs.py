from fastapi import Depends
from redis.asyncio import Redis

from app.core.config import get_settings
from app.dependencies.redis import get_redis
from app.services.job_service import JobService
from app.services.redis_service import RedisService


def get_job_service(redis: Redis = Depends(get_redis)) -> JobService:
    settings = get_settings()
    return JobService(RedisService(redis, job_ttl_seconds=settings.job_ttl_seconds))
