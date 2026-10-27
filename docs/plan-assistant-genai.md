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
  no API key, no cost) with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  (384 dimensions, ~50 languages: Spanish and English questions both work). A hosted adapter
  (e.g. Voyage AI) can be added later without touching the domain.
- **Agent framework**: LangGraph, confined to `infrastructure/agent/`.
- **Cross-context rule**: `assistant` never imports `catalog.domain`. It keeps its own read model
  (`product_documents`) fed through DTOs.
- **Unit tests never call a real model**: `FakeLLMClient` / `FakeEmbeddingClient` at the port
  boundary, same pattern as `FakeProductRepository`.
- **When the LLM fails**: PR 1 answers 503 (there is nothing to retrieve yet). From PR 2 on, a
  deterministic fallback answer (top-k search results without generation) with `fallback_used=true`.
- **Indexing trigger: reindex on demand.** `assistant` owns an `IndexCatalog` use case that reads
  products through its own `CatalogReader` port (DTOs only) and updates `product_documents`.
  `catalog` does not change and does not know `assistant` exists. It runs only via `make reindex`;
  there is no public endpoint while the API has no authentication. Trade-off accepted: the index
  is stale until the next reindex.
  - *Rejected — synchronous inside `CreateProduct` / `UpdateProduct`*: makes `catalog` depend on
    `assistant` and puts embedding latency on every write.
  - *Future evolution (not in PR 2)*: `catalog` publishes `ProductCreated` / `ProductUpdated` /
    `ProductDeleted` domain events through a transactional **outbox**; `assistant` consumes them
    and reindexes only what changed. Needs an event/outbox mechanism the repo does not have yet.

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
  (`product_id UUID PK`, `content TEXT`, `content_hash TEXT`, `embedding vector(384)`,
  `updated_at`), HNSW index on `embedding` (cosine).
- Domain ports —
  - `EmbeddingClient.embed(texts) -> list[list[float]]`.
  - `DocumentSearch.search(embedding, k) -> list[RetrievedDocument]`.
  - `DocumentIndex`: read the stored `product_id → content_hash`, upsert documents, delete
    documents by `product_id`.
  - `CatalogReader.read_all() -> list[CatalogProduct]` — `assistant`'s own view of a product,
    not `catalog`'s DTO. `CatalogReader.missing(ids)` confirms which ids really no longer exist
    (paging is not snapshot-consistent, so absence from `read_all` is not proof of deletion).
  - `EmbeddingClient.model_name` — part of the `content_hash`, so changing the model re-embeds.
- Application —
  - `IndexCatalog` use case, **incremental**: builds each product's document content and its
    `content_hash`; embeds and upserts only new or changed products (Product has no
    `updated_at`, so the hash — over model + content — is the change detector), in batches of
    256; **deletes orphaned documents** only after `CatalogReader.missing` confirms the product no
    longer exists. Returns counts (indexed, unchanged, deleted).
  - `AskAssistant` now embeds the question, retrieves top-k, puts them in the prompt and returns
    them as `sources`. `AnswerDTO` gains `sources` and `fallback_used`.
- Fallback — `AskAssistant` catches `LLMUnavailableError` and returns the top-k results without
  generation, `fallback_used=true`, 200. The 503 from PR 1 no longer reaches the client.
- Infrastructure —
  - `FastEmbedEmbeddingClient` (model, cache dir and `local_files_only` from settings). The
    `Dockerfile` downloads the model at build time; at runtime it is only loaded from disk and
    warmed up in the app lifespan.
  - `SqlAlchemyDocumentSearch` (own short-lived session, so no connection is held during the LLM
    call) / `SqlAlchemyDocumentIndex` (`pgvector.sqlalchemy.Vector`). `RAG_TOP_K` ≤ 40
    (HNSW default `ef_search`).
  - `CatalogReader` adapter: the **only** place `assistant` touches `catalog`. It calls
    `catalog`'s public application API (`ListProducts`, paginated) and maps `ProductDTO` to
    `CatalogProduct`. Never `catalog.domain` or `catalog.infrastructure`.
- UI (input adapters) —
  - `ui/cli/reindex.py` — entry point `python -m contexts.assistant.ui.cli.reindex`. Builds
    `IndexCatalog` with the **same dependency providers** as the API (`ui/dependencies.py`,
    `shared/infrastructure/database.py`), runs it and prints the counts. An input adapter like
    the router; reusable as a Kubernetes `Job` in PR 4.
  - `Makefile` — `make reindex` runs that module in the `api` container.
  - No HTTP endpoint for indexing.
- `pyproject.toml` — add `pgvector`, `fastembed`.
- Tests —
  - Unit with fakes: incremental indexing (unchanged products are not re-embedded), **orphan
    deletion**, retrieval in `AskAssistant`, fallback when the fake LLM raises.
  - Integration against real `db-test`: search adapter (seed three documents, assert the nearest
    one comes back first) and index adapter (upsert, hashes, delete).
  - E2E asserts the fallback flag instead of 503.
- README — mark roadmap step 2 as done and replace "`assistant` never imports `catalog`" with the
  real rule (only the `CatalogReader` adapter, through `catalog`'s application API).

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
  `Job` running `alembic upgrade head`, `Job` running `python -m contexts.assistant.ui.cli.reindex`,
  Postgres with pgvector for local use.
- `make k8s-up` / `make k8s-down` — runs on `kind` locally.
- CI — optional job that creates a kind cluster, applies the manifests and hits `/healthz`.
- Optional — the same image on AWS (App Runner or ECS Fargate + RDS with pgvector).

---

## Done means

- `make lint` and `make test` green; mypy strict passes on the new context.
- README updated: architecture section mentions the `assistant` context; repo description and
  topics set (`fastapi`, `ddd`, `hexagonal-architecture`, `rag`, `pgvector`, `langgraph`).
