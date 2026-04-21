from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Memo Microservice", alias="APP_NAME")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@postgres:5432/memo",
        alias="DATABASE_URL",
    )
    database_disable_prepared_statements: bool | None = Field(
        default=None,
        alias="DATABASE_DISABLE_PREPARED_STATEMENTS",
    )
    database_auto_create: bool = Field(default=True, alias="DATABASE_AUTO_CREATE")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    job_ttl_seconds: int = Field(default=86400, alias="JOB_TTL_SECONDS", gt=0)
    celery_broker_url: str = Field(default="redis://redis:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://redis:6379/2", alias="CELERY_RESULT_BACKEND")
    celery_task_track_started: bool = Field(default=True, alias="CELERY_TASK_TRACK_STARTED")
    celery_result_expires: int = Field(default=86400, alias="CELERY_RESULT_EXPIRES", gt=0)
    celery_result_keyprefix: str = Field(default="memo_", alias="CELERY_RESULT_KEYPREFIX")
    uazapi_base_url: str = Field(default="", alias="UAZAPI_BASE_URL")
    uazapi_token: str = Field(default="", alias="UAZAPI_TOKEN")
    uazapi_instance_id: str | None = Field(default=None, alias="UAZAPI_INSTANCE_ID")
    uazapi_send_text_path: str = Field(default="/send/text", alias="UAZAPI_SEND_TEXT_PATH")
    uazapi_timeout_seconds: float = Field(default=15.0, alias="UAZAPI_TIMEOUT_SECONDS", gt=0)
    uazapi_token_header: str = Field(default="Authorization", alias="UAZAPI_TOKEN_HEADER")
    uazapi_token_prefix: str = Field(default="Bearer", alias="UAZAPI_TOKEN_PREFIX")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
