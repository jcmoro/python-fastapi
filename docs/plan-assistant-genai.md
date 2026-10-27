# Plan — Assistant: GenAI over the catalog (LLM port → RAG → agent → deploy)

Bounded context: `assistant`. Architecture: DDD + Hexagonal (per `CLAUDE.md`).
Goal: answer natural-language questions about the catalog, with the LLM, the embeddings and the
agent framework treated as **adapters behind ports**. The domain never imports `anthropic`,
`langgraph` or `pgvector`.

Delivered in four PRs. Each one is shippable on its own and keeps CI green.

## Decisions taken

- **LLM provider**: Anthropic (`anthropic` SDK, `AsyncAnthropic`). Model and timeout come from
  settings; default to the cheapest current Claude model for dev.
- **Vector store**: `pgvector` inside the existing Postgres. No new infrastructure.
- **Embeddings**: behind an `EmbeddingClient` port. Dev/CI adapter: `fastembed` (local ONNX model,
  no API key, no cost). A hosted adapter (e.g. Voyage AI) can be added later without touching the domain.
- **Agent framework**: LangGraph, confined to `infrastructure/agent/`.
- **Cross-context rule**: `assistant` never imports `catalog.domain`. It keeps its own read model
  (`product_documents`) fed through DTOs.
- **Unit tests never call a real model**: `FakeLLMClient` / `FakeEmbeddingClient` at the port
  boundary, same pattern as `FakeProductRepository`.
- **When the LLM fails**: PR 1 answers 503 (there is nothing to retrieve yet). From PR 2 on, a
  deterministic fallback answer (top-k search results without generation) with `fallback_used=true`.

## Still open (need confirmation)

- **Indexing trigger**: synchronous re-index inside `CreateProduct` / `UpdateProduct` (simple) vs.
  a domain event + background worker (closer to production). _Recommendation_: synchronous now,
  event later.

---

## PR 1 — `LLMClient` port + `AskAssistant` use case (no RAG yet)

### Domain — `src/contexts/assistant/domain/`

- `ports/llm_client.py` — `LLMClient` ABC:
  `async complete(*, system: str, prompt: str, max_tokens: int) -> Completion`.
- `completion.py` — `Completion` frozen dataclass: `text`, `model`, `input_tokens`,
  `output_tokens`, `latency_ms`.
- `exceptions.py` — `InvalidQuestionError(InvalidInputError)`,
  `LLMUnavailableError(ServiceUnavailableError)`.
- `question.py` — `Question` value object: non-empty, max length (e.g. 1,000 chars), stripped.

### Application — `src/contexts/assistant/application/`

- `dtos.py` — `AskCommand(question: str)`, `AnswerDTO(text, usage)`, `UsageDTO(model, input_tokens,
  output_tokens, latency_ms)`.
- `use_cases/ask_assistant.py` — builds the prompt, calls `LLMClient`, maps `Completion` → `AnswerDTO`.
  `LLMUnavailableError` propagates.

### Infrastructure — `src/contexts/assistant/infrastructure/`

- `llm/anthropic_llm_client.py` — `AnthropicLLMClient(LLMClient)`; wraps `AsyncAnthropic`, sets
  timeout and retries once at construction, measures latency, reads token usage from the response.
  Transient SDK errors (connection, timeout, 429, 5xx) become `LLMUnavailableError`; configuration
  errors (400/401/403/404) propagate unchanged (500).

### UI — `src/contexts/assistant/ui/`

- `schemas.py` — `AskRequest`, `AnswerResponse` (Pydantic, `extra="forbid"`).
- `routers/assistant.py` — `POST /assistant/ask`, tag `assistant`.
- `dependencies.py` — per-context DI wiring.

### Shared

- `domain/errors.py` — `ServiceUnavailableError(DomainError)`.
- `infrastructure/exception_handlers.py` — maps `ServiceUnavailableError` to 503.
- `settings.py` — `anthropic_api_key: SecretStr | None`, `llm_model: str`, `llm_timeout_s: float`
  (per attempt), `llm_max_retries: int` (default 0), `llm_max_tokens: int`.
- `.env.example` — the new variables, key left empty.
- `pyproject.toml` — add `anthropic`.

### Tests

- `tests/fakes/llm_client.py` — `FakeLLMClient`, shared by unit and e2e.
- `tests/integration/contexts/assistant/` — adapter against `httpx2.MockTransport`: error
  classification and a single attempt when `max_retries=0`.
- `tests/e2e/test_exception_handlers.py` — each shared domain error maps to its status code.
- `tests/unit/contexts/assistant/` — tests for `Question`
  invariants, happy path, usage propagated to the DTO, `LLMUnavailableError` propagated when the
  fake raises.
- `tests/e2e/test_assistant.py` — override the `LLMClient` dependency with the fake; 200, 422 on
  empty question, 503 when the fake fails.

---

## PR 2 — RAG with pgvector

- `docker-compose.yml` — `db` and `db-test` move to `pgvector/pgvector:pg16`.
- Alembic migration — `CREATE EXTENSION IF NOT EXISTS vector`; table `product_documents`
  (`product_id UUID PK`, `content TEXT`, `embedding vector(<dim>)`, `updated_at`), HNSW index
  on `embedding` (cosine).
- Domain ports — `EmbeddingClient.embed(texts) -> list[list[float]]`;
  `DocumentSearch.search(embedding, k) -> list[RetrievedDocument]`; `DocumentIndex.upsert(...)`.
- Infrastructure — `FastEmbedEmbeddingClient`, `SqlAlchemyDocumentSearch` / `SqlAlchemyDocumentIndex`
  (`pgvector.sqlalchemy.Vector`).
- Application — `IndexProduct` use case (takes a product DTO); `AskAssistant` now retrieves top-k,
  puts them in the prompt and returns them as `sources`. `AnswerDTO` gains `sources` and
  `fallback_used`.
- Fallback — `AskAssistant` catches `LLMUnavailableError` and returns the top-k results without
  generation, `fallback_used=true`, 200. The 503 from PR 1 no longer reaches the client.
- `pyproject.toml` — add `pgvector`, `fastembed`.
- Tests — unit with fakes (including fallback when the fake LLM raises); e2e asserts the fallback
  flag instead of 503; integration for the search adapter against real `db-test`
  (seed three documents, assert the nearest one comes back first).

---

## PR 3 — Agent with LangGraph

- Domain port — `CatalogAgent.run(question) -> AgentResult` (answer, tool calls made, usage).
- Infrastructure — `infrastructure/agent/langgraph_catalog_agent.py`: a small graph with two tools,
  `semantic_search` (uses `DocumentSearch`) and `get_product_by_sku` (reads the read model),
  then a final answer node.
- Guardrails — max steps per run, tool allow-list, same timeout as PR 1 and fallback as PR 2, token usage
  summed across steps.
- `AskAssistant` delegates to the agent behind a setting flag (`assistant_mode = "rag" | "agent"`).
- `pyproject.toml` — add `langgraph`, `langchain-anthropic`.
- Tests — unit with a fake agent; one integration test of the graph wiring with a scripted fake model.

### Evals (not in default CI)

- `tests/evals/` + marker `eval` — ~10 questions with the expected SKU; reports hit rate and cost.
  Run manually with a real key: `make eval`.

---

## PR 4 — Deploy

- `k8s/` — `Deployment` (liveness on `/healthz`), `Service`, `ConfigMap`, `Secret` (template only),
  `Job` running `alembic upgrade head`, Postgres with pgvector for local use.
- `make k8s-up` / `make k8s-down` — runs on `kind` locally.
- CI — optional job that creates a kind cluster, applies the manifests and hits `/healthz`.
- Optional — the same image on AWS (App Runner or ECS Fargate + RDS with pgvector).

---

## Done means

- `make lint` and `make test` green; mypy strict passes on the new context.
- README updated: architecture section mentions the `assistant` context; repo description and
  topics set (`fastapi`, `ddd`, `hexagonal-architecture`, `rag`, `pgvector`, `langgraph`).
