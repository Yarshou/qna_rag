# QnA RAG API

`qna-rag` is a backend-only QnA service built for a constrained assessment setup. It exposes a FastAPI API for chat management, persisted message history, chat events, and grounded assistant responses over a local plain-text knowledge base.

The service supports chat sessions, AI-generated answers, deterministic knowledge retrieval through explicit tool calling, persisted event history, and live event streaming over SSE.

The implementation stays intentionally explicit: FastAPI for HTTP, SQLite with raw SQL for persistence, the OpenAI Python SDK for chat completions, and a local file-based knowledge base with at most two full documents loaded into model context.

## Features / Capabilities

- Chat session creation, listing, and deletion
- Persisted chat message history in SQLite
- AI-generated assistant responses through any OpenAI-compatible provider
- Local knowledge-base retrieval through explicit tool/function calling
- Persisted chat lifecycle events
- Event history endpoint plus polling-backed SSE stream over persisted `chat_events`
- Structured JSON request and workflow logging
- Liveness and readiness health endpoints

## Tech Stack

- Python 3.13
- FastAPI
- SQLite with `aiosqlite` and raw SQL repositories
- OpenAI Python SDK
- Poetry
- Docker

## Repository Layout

- `app/api` - FastAPI routers and HTTP schemas
- `app/services` - application workflows and orchestration
- `app/repositories` - raw SQL access to SQLite
- `app/llm` - OpenAI client wrapper, prompts, and tool execution
- `app/knowledge` - local knowledge loading, indexing, and retrieval
- `app/db` - SQLite connection helpers and schema initialization
- `tests` - integration and unit tests
- `knowledge` - runtime plain-text knowledge files
- `k8s` - Kubernetes manifests (Deployment, Service, PVC, Secret template, optional Ingress template)
- `docs` - supporting design documentation

## Prerequisites

- Python 3.13
- Poetry 2.x
- Docker, if you want to build or run the container image

## Environment Variables

The application reads configuration from `app/envs/.env` by default. Start by copying `app/envs/example.env` to that location.

### Base settings

| Variable | Required | Default | Example | Purpose |
| --- | --- | --- | --- | --- |
| `DEBUG` | Yes | None | `true` | Enables FastAPI debug mode. |
| `APP_PORT` | Yes | None | `8000` | Startup setting required by `Settings`. The provided commands bind the API to port `8000`. |
| `APP_WORKERS` | Yes | None | `1` | Deployment-oriented setting required by `Settings`. SSE tails persisted `chat_events` from SQLite, so live delivery no longer depends on process-local memory, though SQLite still sets practical scaling limits. |
| `DATABASE_PATH` | No | `app/data/qna_rag.sqlite3` | `app/data/qna_rag.sqlite3` | SQLite database location. Relative paths are resolved from the repository root. |
| `KNOWLEDGE_DIR` | Required for message endpoints | `None` | `./knowledge` | Directory containing local plain-text knowledge files. |

### LLM provider — configure ONE of the two options below

The client auto-detects the active provider from which variable group is present. Azure takes precedence when both are configured.

**Option A — Azure OpenAI** (set `AZURE_OPENAI_ENDPOINT`):

| Variable | Required | Default | Example | Purpose |
| --- | --- | --- | --- | --- |
| `AZURE_OPENAI_API_KEY` | Yes | `None` | `replace-me` | Azure OpenAI API key. |
| `AZURE_OPENAI_ENDPOINT` | Yes | `None` | `https://example-resource.openai.azure.com/` | Azure resource base URL. |
| `OPENAI_API_VERSION` | Yes | `None` | `2024-02-15-preview` | Azure OpenAI API version. |
| `AZURE_OPENAI_DEPLOYMENT` | Yes | `None` | `gpt-4.1` | Deployment / model name. |

**Option B — Generic OpenAI-compatible provider** (set `OPENAI_BASE_URL`):

Works with OpenRouter, EPAM DIAL, local Ollama, and any other provider that implements the OpenAI chat-completions API.

| Variable | Required | Default | Example | Purpose |
| --- | --- | --- | --- | --- |
| `OPENAI_API_KEY` | Yes | `None` | `replace-me` | Provider-issued API key. Use `ollama` for local Ollama. |
| `OPENAI_BASE_URL` | Yes | `None` | `https://openrouter.ai/api/v1` | Provider base URL. |
| `OPENAI_MODEL` | Yes | `None` | `meta-llama/llama-3-8b-instruct` | Model identifier passed to the provider. |

Provider examples:

```bash
# OpenRouter
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=<your-openrouter-key>
OPENAI_MODEL=meta-llama/llama-3-8b-instruct

# EPAM DIAL
OPENAI_BASE_URL=https://<dial-host>/openai
OPENAI_API_KEY=<your-dial-key>
OPENAI_MODEL=gpt-4

# Local Ollama
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3
```

Operational note:
`APP_PORT` and `APP_WORKERS` are validated by the settings layer, but only `APP_PORT=8000` is reflected by the provided run commands. The provided local commands still run a simple single-process server, while the SSE implementation reads persisted `chat_events` from SQLite instead of relying on a process-local broker.

## Local Setup

1. Clone the repository and enter the project directory.

   ```bash
   git clone <repository-url> qna_rag
   cd qna_rag
   ```

2. Install dependencies.

   ```bash
   poetry install --with dev
   ```

3. Create the runtime env file.

   ```bash
   cp app/envs/example.env app/envs/.env
   ```

4. Edit `app/envs/.env` and fill in the LLM provider credentials before using `POST /api/v1/chats/{chat_id}/messages`.

5. Start the API locally.

   ```bash
   poetry run uvicorn app.config.app:app --host 0.0.0.0 --port 8000
   ```

6. Verify that the service is up.

   ```bash
   curl http://127.0.0.1:8000/api/v1/healthz
   curl http://127.0.0.1:8000/api/v1/readyz
   ```

## Run Commands

Direct commands:

```bash
poetry run uvicorn app.config.app:app --host 0.0.0.0 --port 8000
poetry run pytest
docker build -t qna-rag .
docker run --rm --env-file app/envs/.env -p 8000:8000 qna-rag
```

Make targets:

```bash
make install
make run
make test
make lint
make format
make docker-build
make docker-run
```

## Test Commands

Run the full test suite:

```bash
poetry run pytest
```

Or through `make`:

```bash
make test
```

Most tests use local fixtures and fakes and run without any LLM credentials. Integration tests in `tests/integration/test_rag.py` hit a real provider and are skipped automatically when no credentials are present. To run them, configure either provider group in `app/envs/.env`.

## Docker Usage

Build the image:

```bash
docker build -t qna-rag .
```

Run the container with the local env file:

```bash
docker run --rm --env-file app/envs/.env -p 8000:8000 qna-rag
```

The SQLite database is stored inside the container at `/qna_rag/app/data/qna_rag.sqlite3`. Without a mounted volume, that data is ephemeral and disappears when the container is removed.

The `knowledge/` directory is copied into the image at build time. If you change knowledge files locally, rebuild the image or run the API outside Docker to use the updated content.

## Kubernetes

Ready-to-use manifests live in `k8s/`:

| File | Purpose |
| --- | --- |
| `k8s/deployment.yaml` | Deployment with probes, resource limits, and PVC volume mount |
| `k8s/service.yaml` | ClusterIP Service (port 80 → 8000) |
| `k8s/pvc.yaml` | PersistentVolumeClaim for SQLite (1 Gi, ReadWriteOnce) |
| `k8s/secret.yaml.example` | Secret template — fill in and apply, **do not commit** |
| `k8s/ingress.yaml.example` | Optional Ingress template for host-based external access and TLS termination |

Quick start:

```bash
# 0. Build and publish the image, or load it into your local cluster runtime.
# For a remote cluster, replace image: qna-rag:latest in k8s/deployment.yaml
# with your registry image before applying manifests.

# 1. Create the secret (do not store real values in source control)
kubectl create secret generic qna-rag-secrets \
  --from-literal=azure-openai-api-key=<your-key>

# 2. Apply the remaining manifests
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

Access options:

- Without Ingress: the current templates deploy correctly with only `Deployment` + `Service` + `PVC` + `Secret`. In that mode the app is reachable only inside the cluster. For local access use `kubectl port-forward svc/qna-rag 8000:80`, or change the Service to `LoadBalancer` / `NodePort` if your cluster/network model allows it.
- With Ingress: apply `k8s/ingress.yaml.example` after replacing the host and ingress class. This is the preferred option when you need stable external HTTP(S) access and TLS termination.

See [docs/production.md](docs/production.md) for guidance on secret management, TLS termination, persistent storage, observability, and scaling considerations.

## API Examples

Liveness check (process alive, no I/O):

```bash
curl http://127.0.0.1:8000/api/v1/healthz
```

Readiness check (DB reachable — used by Kubernetes `readinessProbe`):

```bash
curl http://127.0.0.1:8000/api/v1/readyz
```

Create a chat:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chats \
  -H "Content-Type: application/json" \
  -d '{"title":"Deployment questions"}'
```

List chats:

```bash
curl http://127.0.0.1:8000/api/v1/chats
```

Send a message:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chats/chat-1/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"What does the knowledge base say about deployment readiness?"}'
```

Get message history:

```bash
curl http://127.0.0.1:8000/api/v1/chats/chat-1/messages
```

Get persisted chat events:

```bash
curl "http://127.0.0.1:8000/api/v1/chats/chat-1/events?limit=20"
```

Open the SSE event stream:

```bash
curl -N -H "Accept: text/event-stream" \
  http://127.0.0.1:8000/api/v1/chats/chat-1/events/stream
```

Resume after a previously received event:

```bash
curl -N -H "Accept: text/event-stream" \
  -H "Last-Event-ID: evt-1" \
  http://127.0.0.1:8000/api/v1/chats/chat-1/events/stream
```

Typical SSE payload:

```text
id: evt-1
event: message_received
data: {"id":"evt-1","chat_id":"chat-1","event_type":"message_received","payload":{"message_id":"msg-1"},"created_at":"2026-04-07T10:01:00Z"}
```

## Notes / Limitations

- Live SSE delivery is polling-backed over persisted `chat_events` in SQLite. This removes process-local broker coupling and works across workers or processes that share the same database file, but introduces small polling latency and is not intended for high-fanout realtime workloads.
- Knowledge retrieval only considers plain-text files with supported extensions such as `.txt`, `.md`, `.rst`, and `.text`.
- Full knowledge-file reads are enforced through the tool executor: the model must call `search_knowledge_base` first, may only read `file_id` values returned by the most recent successful search, and can load at most two full knowledge files in one execution flow.
- Assistant message generation requires a configured LLM provider; chat creation, listing, deletion, and health checks do not.

## Documentation Links

- [Architecture overview](docs/architecture.md)
- [Production considerations](docs/production.md)
