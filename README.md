# QnA RAG API

Backend-only QnA service: FastAPI + SQLite + OpenAI-compatible LLM with RAG over local plain-text files via tool calling.

## Structure

```
app/
  api/v1/         FastAPI routers (chats, messages, events, health)
  schemas/        Pydantic request/response models
  services/       application workflows (chat, message, context, notifications)
  repositories/   raw SQL over SQLite (chats, messages, events, knowledge)
  llm/            OpenAI client, prompts, tool definitions & executor
  knowledge/      KB loader, retriever, ranking, sync
  guardrails/     input/output guards
  shared_types/   shared types and utilities
  db/             connection, schema init, schema.sql
  config/         app bootstrap, settings, logging
envs/             example.env (copy to .env)
knowledge/        runtime plain-text KB files
tests/            unit, integration, fixtures
scripts/          helper scripts
k8s/              Deployment, Service, PVC, HPA, Ingress/Secret templates
docs/             architecture & production notes
```

## Quick Start

```bash
poetry install --with dev
cp app/envs/example.env envs/.env   # fill in LLM credentials
make run                                 # or: poetry run uvicorn app.config.app:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/healthz
```

## Configuration

Config is read from `envs/.env`. Required: `DEBUG`, `APP_PORT`, `APP_WORKERS`, `KNOWLEDGE_DIR`.

LLM provider — set **one** group (Azure takes precedence if both present):

- **Azure OpenAI**: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_VERSION`, `AZURE_OPENAI_DEPLOYMENT`
- **OpenAI-compatible** (OpenRouter, DIAL, Ollama, …): `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`

See `envs/example.env` for the full list.

## Common Commands

```bash
make run            # start API
make test           # pytest
make lint           # ruff
make format         # ruff format
make docker-build   # build image
make docker-run     # run container with envs/.env
```

Integration tests in `tests/integration/test_rag.py` require real LLM credentials and are auto-skipped otherwise.

## Documentation

- [Architecture](docs/architecture.md)
- [Production notes](docs/production.md)
