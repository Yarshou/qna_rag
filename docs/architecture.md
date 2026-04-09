# Architecture

## 1. Purpose

This project implements a backend-only QnA agent API built with FastAPI, SQLite, and an OpenAI-compatible API.

The system provides chat sessions, persists message history, and answers user questions using a simple RAG (retrieval augmented generation) workflow over a local knowledge base of plain-text files.

The architecture is intentionally explicit and constraint-driven. It is designed to satisfy the assessment requirements first:

- FastAPI only
- SQLite only
- raw SQL only
- no ORM
- no LangChain / LlamaIndex / similar orchestration frameworks
- OpenAI-compatible SDK
- API only, no UI
- mandatory tool/function calling for KB access
- no more than 2 knowledge files in model context at once

In addition to the core chat and RAG flow, the service exposes chat-processing lifecycle events. These events are persisted in SQLite and delivered to clients in real time through Server-Sent Events (SSE). For this assessment, realtime fan-out is implemented with an in-process `InMemoryEventBroker`.

---

## 2. High-Level Architecture

The system is divided into six main areas:

1. API layer  
   Accepts HTTP requests, validates input, exposes REST endpoints and SSE streams.

2. Application services  
   Orchestrates chat flow, persistence, retrieval, tool execution, final answer generation, and event emission.

3. Persistence layer  
   Stores chats, messages, and chat events in SQLite using raw SQL.

4. LLM integration layer  
   Wraps the OpenAI-compatible client, defines tool schemas, and performs the tool-calling loop.

5. Knowledge layer  
   Loads knowledge files, ranks candidate files, and returns selected document content.

6. Realtime event delivery layer  
   Broadcasts persisted chat events to connected SSE clients through an in-memory broker.

---

## 3. Repository Structure

```text
project-root/
├─ AGENTS.md
├─ Dockerfile
├─ Makefile
├─ pyproject.toml
├─ poetry.lock
├─ docs/
│  └─ architecture.md
├─ app/
│  ├─ api/
│  │  └─ v1/
│  │     ├─ chats.py
│  │     ├─ events.py
│  │     ├─ health.py
│  │     └─ messages.py
│  ├─ config/
│  │  ├─ app.py
│  │  ├─ logging.py
│  │  ├─ settings.py
│  │  └─ setup.py
│  ├─ db/
│  │  ├─ connection.py
│  │  ├─ exceptions.py
│  │  ├─ init.py
│  │  └─ schema.sql
│  ├─ domain/
│  │  ├─ enums.py
│  │  ├─ models.py
│  │  └─ utils.py
│  ├─ events/
│  │  ├─ broker.py
│  │  └─ in_memory.py
│  ├─ knowledge/
│  │  ├─ indexer.py
│  │  ├─ loader.py
│  │  ├─ models.py
│  │  ├─ ranking.py
│  │  └─ retriever.py
│  ├─ llm/
│  │  ├─ client.py
│  │  ├─ exceptions.py
│  │  ├─ prompts.py
│  │  ├─ tool_executor.py
│  │  └─ tools.py
│  ├─ repositories/
│  │  ├─ chats.py
│  │  ├─ events.py
│  │  ├─ messages.py
│  │  └─ utils.py
│  ├─ schemas/
│  │  ├─ chats.py
│  │  ├─ common.py
│  │  ├─ events.py
│  │  └─ messages.py
│  └─ services/
│     ├─ chat_service.py
│     ├─ context_service.py
│     ├─ message_service.py
│     └─ notification_service.py
└─ tests/
   ├─ fixtures/
   │  └─ knowledge/
   ├─ integration/
   └─ unit/
```

`app/events` is the only new area introduced for realtime delivery. It does not own business logic or persistence. Its responsibility is transient fan-out of already-created chat events.

---

## 4. Layer Responsibilities

| Layer | Responsibility | Must contain | Must not contain |
| --- | --- | --- | --- |
| `app/api` | HTTP boundary | routes, request/response schemas, SSE endpoint, status-code mapping | SQL, retrieval logic, OpenAI calls |
| `app/services` | application orchestration | chat flow, message flow, RAG coordination, event emission | raw SQL, HTTP-specific code |
| `app/repositories` | persistence access | SQLite queries, row mapping | business workflow logic, LLM calls |
| `app/llm` | provider integration | OpenAI client, tool schemas, tool loop | direct DB access, HTTP handlers |
| `app/knowledge` | KB loading and retrieval | indexing, search, ranking, file reading | API logic, chat orchestration |
| `app/events` | realtime fan-out | broker abstraction, in-memory pub/sub for SSE | persistence logic, business workflow logic |
| `app/db` | low-level DB setup | connection and schema init | business logic |
| `tests` | validation | integration and focused unit tests | production code |

---

## 5. Dependency Rules

Allowed dependency flow:

- `api -> services`
- `api -> events` only for SSE subscription wiring
- `services -> repositories`
- `services -> llm`
- `services -> knowledge`
- `services -> events`
- `repositories -> db`
- `knowledge -> filesystem / index data`
- `llm -> OpenAI-compatible provider`

Forbidden dependency flow:

- `api -> db`
- `api -> repositories` directly, if avoidable
- `api -> llm`
- `repositories -> llm`
- `repositories -> api`
- `knowledge -> api`
- `events -> repositories`
- `events -> llm`

Interpretation:

- API should not know how the agent works internally.
- Repositories should not know anything about prompts, tools, or provider behavior.
- Knowledge retrieval should be reusable independently of FastAPI.
- Event delivery should be replaceable without changing business logic.
- The notification flow should publish already-created domain events rather than inventing a second event model.

---

## 6. Core Runtime Flows

### 6.1 Chat Creation Flow

1. Client sends a request to create a chat.
2. API validates the request.
3. `ChatService` creates the chat record via repository.
4. API returns chat metadata.

### 6.2 Message Processing Flow

1. Client posts a user message into a chat.
2. API validates the request and calls `MessageService`.
3. Service persists the user message.
4. Service emits `message_received`.
5. Service emits `message_processing`.
6. Service loads relevant chat context.
7. Service calls the LLM with:
   - system instruction
   - chat history
   - tool definitions
8. Model may respond with:
   - a final answer directly, or
   - one or more tool calls
9. Tool calls are executed through `ToolExecutor`.
10. Tool results are sent back to the model.
11. Model produces the final grounded answer.
12. Service persists the assistant response.
13. Service emits `message_completed`, or `message_failed` on error.
14. API returns the response payload.

### 6.3 Chat Event Flow

Each chat-processing event follows two paths:

1. Durable path  
   `NotificationService` stores the event in SQLite through `EventsRepository`.

2. Realtime path  
   `NotificationService` publishes the same event into `InMemoryEventBroker`.

SSE clients subscribed to the relevant `chat_id` receive the event immediately from the broker. REST clients can still query the persisted event history later.

### 6.4 SSE Subscription Flow

1. Client opens `GET /api/v1/chats/{chat_id}/events/stream`.
2. API validates that the chat exists.
3. API subscribes the connection to `InMemoryEventBroker` for that `chat_id`.
4. API streams events as `text/event-stream`.
5. On disconnect, the subscription is removed.
6. If reconnect support is needed, missed events can be replayed from SQLite using the last received event id or timestamp.

---

## 7. Realtime Notifications Design

### 7.1 Why SSE

The project needs one-way delivery of chat status updates from backend to frontend:

- message received
- processing started
- tool called
- message completed
- message failed

SSE is preferred here because:

- the transport is server-to-client only
- the frontend does not need bidirectional communication
- event ordering maps naturally to the existing `chat_events` model
- the implementation is simpler than WebSockets
- updates are more timely than polling

### 7.2 Why Not Polling

Polling remains a fallback option, but it is not the primary design because it:

- introduces avoidable latency
- increases request overhead
- duplicates work when no new events exist

The persisted `/events` endpoint remains useful for history and replay, not as the main live update channel.

### 7.3 Broker Design

For this assessment, realtime fan-out is handled by `InMemoryEventBroker`.

Responsibilities:

- keep per-chat subscriber lists
- publish domain events to active subscribers
- remain transient and process-local

Non-responsibilities:

- persistence
- event creation
- event schema ownership

This keeps the broker replaceable. A future multi-instance deployment could swap the broker implementation without changing the public API or the core notification workflow.

### 7.4 Current Scaling Boundary

`InMemoryEventBroker` is appropriate for:

- local development
- tests
- single-process deployment
- assessment scope

It is not a cross-process or multi-instance event bus. That limitation is acceptable here because SQLite is also an explicit assessment constraint. The architecture remains production-aware by isolating the broker behind a dedicated layer and keeping event history durable in SQLite.

---

## 8. RAG Design

### 8.1 RAG Goal

The system must answer questions using a local knowledge base without loading the whole KB into the model context.

Given the task constraints, the retrieval system must satisfy:

- many files in KB
- each file is relatively small
- full KB is larger than model context
- at most 2 KB files can be included in model context

### 8.2 Retrieval Strategy

The retrieval flow is intentionally split into two steps:

`search_knowledge_base(query)`  
Returns a compact list of candidate files with metadata and snippets.

`read_knowledge_file(file_id)`  
Returns full content only for selected files.

This split matters because it prevents naive prompt stuffing and keeps tool usage explicit.

### 8.3 Tool-Calling Model

The model must access KB only through tool/function calling.

Recommended tools:

- `search_knowledge_base(query: str) -> KnowledgeSearchResult`
- `read_knowledge_file(file_id: str) -> KnowledgeDocument | None`

Tool outputs should be structured and deterministic.

Example search result fields:

- `file_id`
- `filename`
- `score`
- `snippet`

Example read result fields:

- `file_id`
- `filename`
- `content`

### 8.4 Grounding Rules

The final answer may only be grounded on:

- system instructions
- selected chat history
- retrieved KB data returned by tools

The final model context must never contain more than 2 full KB files.

### 8.5 Retrieval Implementation Direction

For this assessment, file-level lexical retrieval is sufficient because:

- the KB is local and text-based
- the implementation remains explainable
- retrieval behavior is deterministic
- full selected files are small enough to load when chosen

The design intentionally avoids specialized orchestration frameworks and hidden retrieval abstractions.

---

## 9. Chat Context Management

Conversation context and KB grounding are separate concerns.

### 9.1 Chat Context

Chat context contains:

- prior user messages
- prior assistant messages
- system prompt

### 9.2 Grounding Context

Grounding context contains:

- tool results
- selected file content
- no more than 2 full files

### 9.3 Why This Separation Matters

Without separation, the system tends to:

- overfill prompt context
- blur source of truth
- make debugging harder
- make retrieval quality unpredictable

The architecture therefore keeps:

- conversation memory in the chat/message layer
- knowledge grounding in the retrieval layer

---

## 10. Persistence Design

SQLite stores durable state for the service.

### 10.1 Main Persisted Entities

| Entity | Purpose |
| --- | --- |
| `chats` | chat session identity and lifecycle |
| `messages` | ordered user/assistant message history |
| `chat_events` | durable lifecycle event history |

### 10.2 Minimal Schema Direction

`chats`

- `id`
- `created_at`
- `title`
- `status`

`messages`

- `id`
- `chat_id`
- `role`
- `content`
- `created_at`
- `metadata_json`

`chat_events`

- `id`
- `chat_id`
- `event_type`
- `payload_json`
- `created_at`

Exact column naming may change, but the design intent is stable:

- reconstruct chat history reliably
- reconstruct processing lifecycle reliably
- support both REST event history and SSE replay
- keep event persistence independent from live delivery

---

## 11. Observability and Operational Notes

- Request lifecycle should be logged with stable request ids.
- Message-processing milestones should be logged with chat and message identifiers.
- Tool invocations should be logged without exposing sensitive payloads.
- Provider failures should be logged explicitly.
- Event delivery should remain observable through persisted `chat_events` even if no SSE client is connected.

This ensures the system remains debuggable even though the realtime delivery path is transient.
