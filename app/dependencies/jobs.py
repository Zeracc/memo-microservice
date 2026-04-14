from fastapi import Depends
from redis.asyncio import Redis

from app.dependencies.redis import get_redis
from app.services.job_service import JobService
from app.services.redis_service import RedisService


def get_job_service(redis: Redis = Depends(get_redis)) -> JobService:
    return JobService(RedisService(redis))
