# QnA RAG API

`qna-rag` is a backend-only QnA service built for a constrained assessment setup. It exposes a FastAPI API for chat management, persisted message history, chat events, and grounded assistant responses over a local plain-text knowledge base.

The service supports chat sessions, AI-generated answers, deterministic knowledge retrieval through explicit tool calling, persisted event history, and live event streaming over SSE.

The implementation stays intentionally explicit: FastAPI for HTTP, SQLite with raw SQL for persistence, the OpenAI Python SDK for Azure OpenAI-compatible calls, and a local file-based knowledge base with at most two full documents loaded into model context.

## Features / Capabilities

- Chat session creation, listing, and deletion
- Persisted chat message history in SQLite
- AI-generated assistant responses through Azure OpenAI-compatible chat completions
- Local knowledge-base retrieval through explicit tool/function calling
- Persisted chat lifecycle events
- Event history endpoint plus polling-backed SSE stream over persisted `chat_events`
- Structured JSON request and workflow logging
- Health endpoint

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
- `docs` - supporting design documentation

## Prerequisites

- Python 3.13
- Poetry 2.x
- Docker, if you want to build or run the container image

## Environment Variables

The application reads configuration from `app/envs/.env` by default. Start by copying `app/envs/example.env` to that location.

| Variable | Required | Default | Example | Purpose |
| --- | --- | --- | --- | --- |
| `DEBUG` | Yes | None | `true` | Enables FastAPI debug mode. |
| `APP_PORT` | Yes | None | `8000` | Startup setting required by `Settings`. The provided commands bind the API to port `8000`. |
| `APP_WORKERS` | Yes | None | `1` | Deployment-oriented setting required by `Settings`. SSE tails persisted `chat_events` from SQLite, so live delivery no longer depends on process-local memory, though SQLite still sets practical scaling limits. |
| `DATABASE_PATH` | No | `app/data/qna_rag.sqlite3` | `app/data/qna_rag.sqlite3` | SQLite database location. Relative paths are resolved from the repository root. |
| `KNOWLEDGE_DIR` | Required for message endpoints | `None` | `./knowledge` | Directory containing local plain-text knowledge files. `MessageService` initializes the knowledge tool executor eagerly, so `/messages` routes need this configured. |
| `AZURE_OPENAI_API_KEY` | Required for assistant responses | `None` | `replace-me` | Azure OpenAI API key. |
| `AZURE_OPENAI_ENDPOINT` | Required for assistant responses | `None` | `https://example-resource.openai.azure.com/` | Azure OpenAI endpoint base URL. |
| `OPENAI_API_VERSION` | Required for assistant responses | `None` | `2024-02-15-preview` | Azure OpenAI API version. |
| `AZURE_OPENAI_DEPLOYMENT` | Required for assistant responses | `None` | `gpt-4.1` | Azure OpenAI deployment name passed as the model identifier. |

Operational note:
`APP_PORT` and `APP_WORKERS` are validated by the settings layer, but only `APP_PORT=8000` is reflected by the provided run commands. The provided local commands still run a simple single-process server, while the SSE implementation itself now reads persisted `chat_events` from SQLite instead of relying on a process-local broker.

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

4. Edit `app/envs/.env` and replace the Azure OpenAI placeholders before using `POST /api/v1/chats/{chat_id}/messages`.

5. Start the API locally.

   ```bash
   poetry run uvicorn app.config.app:app --host 0.0.0.0 --port 8000
   ```

6. Verify that the service is up.

   ```bash
   curl http://127.0.0.1:8000/api/v1/healthz
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

The current test suite uses local fixtures and fakes for API-level coverage, so the default path does not require live Azure credentials.

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

## API Examples

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/healthz
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
- The agent can load at most two full knowledge files into model context.
- Assistant message generation requires valid Azure OpenAI settings; chat creation, listing, deletion, and health checks do not.

## Documentation Links

- [Architecture overview](docs/architecture.md)
