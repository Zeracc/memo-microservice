# Memo Microservice
Microsserviço responsável pelo processamento assíncrono de notificações, projetado com foco em escalabilidade, resiliência e desacoplamento.
A aplicação expõe uma API REST para criação e acompanhamento de notificações, utilizando uma arquitetura baseada em fila (queue) e workers para garantir processamento eficiente e confiável.

## Environment

Cofigure a aplicação e o worker da seguinte forma:

```env
APP_NAME=Memo Microservice
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/memo
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
psql postgresql://postgres:postgres@localhost:5432/memo -f migrations/001_create_notifications.sql
```

With Docker Compose:

```bash
docker compose up --build
```



  Principais Funcionalidades
Processamento assíncrono de notificações (padrão fila + worker)
Suporte à idempotência via external_id
Mecanismo de retry com controle de tentativas
Rastreamento de jobs e status de execução
Priorização de mensagens (low, normal, high)
Abstração de provider (preparado para integração com APIs externas)
Tratamento de falhas com registro de erros
Expiração de jobs via TTL (Redis)
Separação clara entre camada de API e processamento

  Arquitetura
A API recebe a requisição e persiste no banco de dados
Um job é criado e enviado para a fila (Redis)
Workers consomem a fila e processam as notificações
O status é atualizado no banco e no sistema de jobs
  Stack Tecnológica
Backend: FastAPI
Linguagem: Python
Banco de Dados: PostgreSQL (via Supabase)
Fila / Broker: Redis
Processamento Assíncrono: Worker custom (preparado para evolução com Celery)
Containerização: Docker
Integração futura: APIs de mensageria (ex: Uazapi)

  Conceitos Aplicados
Arquitetura de microsserviços
Processamento assíncrono com fila
Design de APIs idempotentes
Estratégias de retry e tolerância a falhas
Desacoplamento entre serviços
Base preparada para evolução para service bus (RabbitMQ, Kafka, etc.)

  Casos de Uso
Envio de notificações (WhatsApp, SMS, Email)
Processamento de tarefas em background
Integração com APIs externas
Sistemas orientados a eventos

  Objetivo do Projeto

Demonstrar a construção de um microsserviço backend com características de produção, preparado para escalar e evoluir para arquiteturas mais robustas com mensageria avançada (service bus), mantendo boas práticas de engenharia de software.
