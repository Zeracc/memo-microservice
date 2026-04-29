#Microservice

## Environment

Configure the application and worker with:

```env
APP_NAME=Microservice
DATABASE_URL=
DATABASE_AUTO_CREATE=true
REDIS_URL=redis://redis:6379/0
JOB_TTL_SECONDS=86400
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
CELERY_TASK_TRACK_STARTED=true
CELERY_RESULT_EXPIRES=86400
CELERY_RESULT_KEYPREFIX=memo_
UAZAPI_BASE_URL=https://your-uazapi-host
UAZAPI_TOKEN=your-uazapi-token
UAZAPI_INSTANCE_ID=your-instance-id
UAZAPI_SEND_TEXT_PATH=/send/text
UAZAPI_TIMEOUT_SECONDS=15
UAZAPI_TOKEN_HEADER=Authorization
UAZAPI_TOKEN_PREFIX=Bearer
```

## Run locally

API:

```bash
python -m uvicorn app.main:app --reload
```

Celery worker:

```bash
python -m celery -A app.core.celery_app.celery_app worker --loglevel=info
```

Postgres:

```bash
docker run --name memo-postgres -e POSTGRES_DB=memo -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16-alpine
```

Redis:

```bash
docker run --name memo-redis -p 6379:6379 -d redis:7-alpine
```

Migration SQL:

```bash
psql postgresql://postgres resto da url -f migrations/001_create_notifications.sql
```

With Docker Compose:

```bash
docker compose up --build
```
