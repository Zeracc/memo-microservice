from fastapi import Request
from redis.asyncio import Redis

from app.core.config import get_settings


def create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_redis_client_for_worker() -> Redis:
    settings = get_settings()
    return create_redis_client(settings.redis_url)
