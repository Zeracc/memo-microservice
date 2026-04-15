# Memo Microservice

## Environment

Configure the application and worker with:

```env
APP_NAME=Memo Microservice
REDIS_URL=redis://redis:6379/0
JOB_TTL_SECONDS=86400
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
CELERY_TASK_TRACK_STARTED=true
CELERY_RESULT_EXPIRES=86400
CELERY_RESULT_KEYPREFIX=memo_
```

## Run locally

API:

```bash
uvicorn app.main:app --reload
```

Celery worker:

```bash
celery -A app.core.celery_app.celery_app worker --loglevel=info
```

With Docker Compose:

```bash
docker compose up --build
```
