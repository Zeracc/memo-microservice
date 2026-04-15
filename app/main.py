from contextlib import asynccontextmanager
import logging
import time
from typing import AsyncIterator

from fastapi import FastAPI, Request
from starlette.responses import Response

from app.api.jobs import router as jobs_router
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.dependencies.redis import create_redis_client


configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Reuse one Redis client across the app lifecycle.
    redis_client = create_redis_client(settings.redis_url)
    app.state.redis = redis_client

    logger.info("Starting application: %s", settings.app_name)
    try:
        yield
    finally:
        await redis_client.aclose()
        logger.info("Application shutdown complete")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)
app.include_router(jobs_router)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000

    logger.info(
        "%s %s -> %s (%.2f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response
