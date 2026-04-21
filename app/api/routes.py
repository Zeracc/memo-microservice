import logging

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies.redis import get_redis


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", tags=["root"])
async def read_root() -> dict[str, str]:
    return {"message": "Welcome to the FastAPI microservice starter."}


@router.get("/health", tags=["health"])
async def health_check(
    redis: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    try:
        await redis.ping()
    except RedisError as exc:
        logger.warning("Health check failed because Redis is unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        ) from exc

    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Health check failed because database is unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc

    return {"status": "ok"}
