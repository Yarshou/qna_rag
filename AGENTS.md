## Project Mission
Build a backend-only QnA agent API using FastAPI, SQLite, and an OpenAI-compatible API.

The system must implement a simple RAG workflow over local plain-text knowledge files using OpenAI tool/function calling.
No specialized orchestration libraries (LangChain, LlamaIndex, etc.) are allowed.

Primary goal: satisfy assessment requirements with a clear, production-aware architecture.

---

## Non-Negotiable Constraints

- Use FastAPI for the API layer
- Every domain must have __init__.py file
- Use Poetry for dependency management
- Use OpenAI Python SDK with Azure OpenAI configuration via environment variables
- Use SQLite for persistence
- Do not use SQLAlchemy or any ORM
- Do not use LangChain, LlamaIndex, Haystack, or similar libraries
- Use OpenAI Python SDK with base URL and API key from environment variables
- No UI (API only)
- Persist all chats, messages, and relevant processing data
- Use pytest with async support
- Knowledge base is a directory of plain text files
- Never inject the entire KB into model context
- At most 2 knowledge files may be included in model context simultaneously
- Tool/function calling is mandatory for KB access

---

## Architecture Principles

- Keep FastAPI routers thin (no business logic)
- Place application logic in services
- Application configuration in config level
- Isolate database access in repositories using raw SQL
- Isolate LLM interaction in a dedicated module
- Isolate knowledge base loading, indexing, and retrieval
- Prefer explicit data flow over hidden abstractions
- Avoid unnecessary layers and overengineering
- Keep modules cohesive and focused
- Use async for all I/O boundaries

---

## Directory Responsibilities

- app/api: HTTP routes and request/response schemas only
- app/services: application workflows and orchestration
- app/repositories: SQLite access using raw SQL only
- app/llm: OpenAI client, tool definitions, tool execution
- app/knowledge: file loading, indexing, retrieval logic
- app/db: connection and schema initialization
- tests: integration and unit tests

---

## RAG Rules

- The assistant must use tool/function calling to access the knowledge base
- Define explicit tools such as:
  - search_knowledge_base(query)
  - read_knowledge_file(file_id)
- Always perform retrieval before loading full file content
- Load full content only for selected top files
- Never include more than 2 KB files in final model context
- Do not expose arbitrary filesystem access to the model
- Keep retrieval deterministic and explainable

---

## Coding Rules

- Use Python 3.13
- Use type hints across the codebase
- Use Pydantic for API schemas
- Keep functions small and focused
- Prefer explicit error handling over silent failures
- Use structured logging for key operations
- Do not introduce new dependencies without strong justification
- Avoid large multipurpose modules

---

## Testing Rules

- Cover all public API workflows with happy-path tests
- Include integration tests for:
  - chat lifecycle
  - message flow
  - RAG pipeline
- External LLM calls may be real and env-configured
- Mark provider-dependent tests explicitly
- Use small, deterministic fixtures
- Store KB test data under tests/fixtures/knowledge

---

## Operational Requirements

- Configuration must come from environment variables
- Provide health and readiness endpoints
- Initialize SQLite schema explicitly and idempotently
- Docker must use multi-stage build
- Container must run as non-root user
- Log request flow, tool calls, and provider errors

---

## Rule Loading

Before starting any task:

1. Read this AGENTS.md
2. Identify affected area
3. Load relevant rules from `.codex/rules/`
4. Apply `.codex/rules/` for execution constraints
5. Use `.codex/skills/` if a matching workflow exists

Minimum rule loading:

- Always read `.codex/rules`
- Load additional rules depending on the task:
  - api.mdc
  - db.mdc
  - rag.mdc
  - llm.mdc
  - tests.mdc
  - docker.mdc

---

## Rule Precedence

When rules conflict:

1. Assessment requirements
2. AGENTS.md
3. Most specific `.codex/rules/*.rules`
4. Existing project conventions

---

## Change Policy

- Make minimal coherent changes
- Do not refactor unrelated code
- Do not introduce new dependencies without need
- Update tests when behavior changes
- Update documentation when API or config changes
- Preserve established project structure