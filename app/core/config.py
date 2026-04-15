from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Memo Microservice", alias="APP_NAME")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    job_ttl_seconds: int = Field(default=86400, alias="JOB_TTL_SECONDS", gt=0)
    celery_broker_url: str = Field(default="redis://redis:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://redis:6379/2", alias="CELERY_RESULT_BACKEND")
    celery_task_track_started: bool = Field(default=True, alias="CELERY_TASK_TRACK_STARTED")
    celery_result_expires: int = Field(default=86400, alias="CELERY_RESULT_EXPIRES", gt=0)
    celery_result_keyprefix: str = Field(default="memo_", alias="CELERY_RESULT_KEYPREFIX")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
