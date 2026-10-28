<div align="center">

# python-fastapi

**Generative AI on FastAPI, done the clean way.**

A reference **Generative AI backend** in Python: a **RAG** assistant that answers from a product catalog, with an optional **LangGraph agent** that recommends products by rules, not by the model's word. Built with **FastAPI**, **Domain-Driven Design (DDD)** and the **Hexagonal (Ports & Adapters)** pattern. The LLM, the embeddings and the vector store are adapters behind ports — swap providers, fake them in tests, and keep them out of your domain.

[![CI](https://github.com/jcmoro/python-fastapi/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jcmoro/python-fastapi/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-272%20passing-2e7d32?style=flat)
![Architecture](https://img.shields.io/badge/architecture-DDD%20%2B%20Hexagonal-2e7d32?style=flat)
![mypy](https://img.shields.io/badge/mypy-strict-1565c0?style=flat)
![GenAI](https://img.shields.io/badge/GenAI-RAG%20%2B%20agent-6a1b9a?style=flat)
![LangGraph](https://img.shields.io/badge/agent-LangGraph-1c3c3c?style=flat)
![pgvector](https://img.shields.io/badge/vectors-pgvector-336791?style=flat&logo=postgresql&logoColor=white)
![Claude](https://img.shields.io/badge/LLM-Claude-D97757?style=flat&logo=anthropic&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?style=flat&logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat&logo=pydantic&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?style=flat&logo=docker&logoColor=white)

### [**→ What works today**](#what-works-today)

[Why this project](#why-this-project) ·
[Roadmap](#roadmap) ·
[Quick Start](#quick-start) ·
[Architecture](#architecture) ·
[Testing](#testing) ·
[Issues](https://github.com/jcmoro/python-fastapi/issues)

</div>

---

## Why this project

Most GenAI demos wire the SDK straight into the route handler. This one treats the LLM like any other infrastructure dependency:

- **The LLM is a port.** The domain defines `LLMClient`; `AnthropicLLMClient` is just one adapter. The domain and application layers never import `anthropic`.
- **Retrieval is a port too.** `EmbeddingClient` and `DocumentSearch` are ports; embeddings run locally with a multilingual model (no API key, no cost) and vectors live in the existing Postgres with `pgvector`.
- **Indexing is explicit and incremental.** `make reindex` re-embeds only products whose content or embedding model changed (a `content_hash` per document), in batches, and deletes documents only after confirming their product no longer exists. `catalog` doesn't know the assistant exists.
- **Tests never call a real model.** Unit and e2e tests use fakes at the port boundary (`FakeLLMClient`, `FakeEmbeddingClient`, `FakeDocumentSearch`). The real LLM adapter is tested against a mocked HTTP transport, and the vector adapters against a real pgvector database.
- **Failures have a contract.** If the LLM is unavailable (connection, timeout, 429, 5xx), or its answer is cut off by the token limit or refused, the answer still comes back — **200** with the retrieved products and `fallback_used: true`. Configuration errors (bad key, unknown model) are not disguised as outages.
- **The model doesn't pick the product.** In agent mode, `recommend_candidate` asks Claude two yes/no rubric questions per candidate (3 samples each) and a pure `select()` function filters, ranks and applies thresholds. `recommendation` comes only from that selection, never from the model's text.
- **The agent is bounded.** At most `AGENT_MAX_TOOL_CALLS` tool calls per question; past that it answers in RAG mode with what it retrieved. A transient failure mid-run keeps the recommendation and sources gathered so far.
- **Evals are opt-in and honest.** `make eval` runs the selector and the full agent against a fixed 20-product dataset in its own database, reports results as counts, and stops if the API rate-limits too much. They never run in `make test` or CI.
- **Latency is bounded.** `LLM_TIMEOUT_S` applies per attempt and `LLM_MAX_RETRIES` defaults to 0, so the worst case is `timeout * (retries + 1)`.
- **Every answer reports its cost.** Responses include the model used, input/output tokens and latency.

---

## What works today

Index the catalog, then ask. `POST /assistant/ask` retrieves the most similar products, answers from them and returns them as `sources`.

```bash
make reindex                    # → indexed=3 unchanged=0 deleted=0 (incremental on later runs)

curl -s -X POST http://localhost:8000/assistant/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "Which widgets cost less than 20 EUR?"}'
```

Example response (values are illustrative):

```json
{
  "text": "…",
  "sources": [
    {
      "product_id": "8f1c…",
      "content": "SKU: PROD-1\nName: Blue widget\nPrice: 19.99 EUR",
      "score": 0.61
    }
  ],
  "fallback_used": false,
  "usage": {
    "model": "claude-haiku-5-5",
    "input_tokens": 52,
    "output_tokens": 87,
    "latency_ms": 1240
  },
  "recommendation": null
}
```

`recommendation` is always present. It is `null` in `rag` mode, and in `agent` mode when the agent did not run the selector. When the selector ran, it is an object: `{"product_id", "sku", "score", "reason"}`, where `reason` is `chosen`, `below_threshold` or `no_assessments`, and `product_id`, `sku` and `score` are non-null only when `reason` is `chosen`.

Agent mode is off by default. Turn it on with `ASSISTANT_MODE=agent`: the agent then has three tools, `semantic_search`, `get_product_by_sku` and `recommend_candidate`.

| Status | When |
|--------|------|
| `200`  | The model answered from the retrieved products. Also when the LLM is unavailable (connection, timeout, 429, 5xx) or its answer is cut off by the token limit or refused: then `fallback_used` is `true`, `usage` is `null` and the text lists the retrieved products. |
| `422`  | Empty or blank question, more than 1,000 characters, or unknown fields. |
| `500`  | Misconfiguration: missing or invalid API key, unknown model, invalid request. |

The index reflects the catalog as of the last `make reindex`. There is deliberately no indexing endpoint while the API has no authentication.

---

## Roadmap

Delivered as small, shippable PRs. Full plan: [`docs/plan-assistant-genai.md`](docs/plan-assistant-genai.md).

| Step | Scope | Status |
|------|-------|--------|
| 1 | `LLMClient` port, Anthropic adapter, `POST /assistant/ask`, failure contract | ✅ Done |
| 2 | **RAG** with `pgvector` in the existing Postgres: local multilingual embeddings behind a port, incremental `make reindex`, top-k retrieval, `sources` in the answer, deterministic fallback when the LLM fails | ✅ Done |
| 3 | **Agent** with LangGraph: candidate selection by rubric and pure `select()` (3a), agent with catalog tools, step limit and summed token usage (3b), evals E1–E4 | ✅ Done |
| 4 | **Deploy**: Kubernetes manifests, local `kind` cluster, optional cloud target | ⏳ Planned |

---

## Stack

| Layer            | Choice                                                   |
|------------------|----------------------------------------------------------|
| Language         | Python ≥ 3.10 (type hints required)                      |
| Web framework    | FastAPI + Uvicorn                                        |
| LLM              | Anthropic Claude (`anthropic` SDK), behind `LLMClient`   |
| Embeddings       | `fastembed`, multilingual MiniLM (384 dims), local        |
| Vector store     | `pgvector` (HNSW, cosine) in PostgreSQL 16               |
| Validation       | Pydantic v2                                              |
| Settings         | `pydantic-settings` (`BaseSettings`)                     |
| Serialization    | FastAPI native (Pydantic core)                           |
| Tests            | `pytest`, `pytest-asyncio`, `httpx`                      |
| Static checks    | `pylint`, `ruff`, `mypy`                                 |
| Packaging        | `pyproject.toml`                                         |
| Container / CLI  | Docker + `make`                                          |

---

## Architecture

DDD + Hexagonal. Each **bounded context** is a vertical slice with four layers:

| Layer            | Allowed dependencies                | Responsibility                                                       |
|------------------|-------------------------------------|----------------------------------------------------------------------|
| `domain/`        | none                                | Entities, value objects, domain services, **port** interfaces.       |
| `application/`   | `domain/`                           | Use cases (commands and queries), DTOs, application services.        |
| `infrastructure/`| `domain/`, `application/`           | Adapter implementations (repositories, LLM clients, persistence).    |
| `ui/`            | `application/`, DTOs                | FastAPI routers and Pydantic schemas. Translates HTTP ↔ use cases.   |

**Direction of dependencies points inward.** Outer layers depend on inner ones, never the reverse.

Cross-context contracts travel as **DTOs only** — no shared domain models between bounded contexts. `assistant` reaches `catalog` in exactly one adapter, `ListProductsCatalogReader`, through `catalog`'s application API (`ListProducts` + `ProductDTO`), plus its own dependency wiring. It never imports `catalog.domain` or `catalog.infrastructure`, and `catalog` never imports `assistant`.

### Project Layout

Two contexts so far: `catalog` (products CRUD) and `assistant` (GenAI). Subdirectories are introduced only when they earn their place — single-file modules are preferred for the first occupant of each layer.

```
src/
  contexts/
    catalog/
      domain/                          # No framework imports.
        product.py                     # Entity (frozen dataclass + invariants)
        exceptions.py                  # Domain errors (extend shared.domain.errors)
        ports/
          product_repository.py        # ABC defining the persistence contract
      application/                     # Depends on domain only.
        dtos.py                        # ProductDTO, command/query carriers
        use_cases/
          create_product.py
          get_product.py
          list_products.py
          update_product.py
          delete_product.py
      infrastructure/                  # Adapters; the only place SQLAlchemy lives.
        persistence/
          models.py                    # ProductModel (ORM)
          mappers.py                   # to_domain / to_model
          sqlalchemy_product_repository.py
      ui/                              # FastAPI surface.
        schemas.py                     # Pydantic request/response models
        routers/products.py            # Endpoints (POST/GET/PATCH/DELETE)
        dependencies.py                # Per-context DI wiring
    assistant/
      domain/                          # No anthropic, no FastAPI.
        question.py                    # Value object (stripped, non-empty, ≤ 1,000 chars)
        completion.py                  # Completion: text, model, tokens, latency
        catalog_product.py             # assistant's own view of a product
        product_document.py            # ProductDocument (catalog fields, content, content_hash)
        retrieved_document.py          # Search hit with cosine similarity
        candidate.py                   # Candidate, RubricAnswers, Assessment (+ usage, failure reason)
        assessment_usage.py            # API calls and tokens per assessment
        rubric.py                      # The two yes/no rubric questions, defined once
        selection.py                   # select(): filter, rank, tie-break, threshold — pure
        agent.py                       # AgentResult, stop reasons, AgentUnavailableError (partial state)
        exceptions.py                  # InvalidQuestionError, LLMUnavailableError, InvalidAssessmentError
        ports/
          llm_client.py                # LLMClient ABC — documents which failures it raises
          embedding_client.py          # One embedding per text, same order
          document_search.py           # Top-k, most similar first
          document_index.py            # Hashes, upsert, delete
          catalog_reader.py            # Products from the catalog, no duplicates
          candidate_assessor.py        # One candidate per call; probabilities in [0, 1]
          catalog_agent.py             # Step limit, model_incomplete, partial state on failure
      application/
        dtos.py                        # Ask/Answer/Source/Usage/IndexReport/Candidate/Recommendation DTOs
        use_cases/
          ask_assistant.py             # Embed → retrieve → generate, or the agent; fallback without generation
          index_catalog.py             # Incremental reindex + orphan deletion (before upsert)
          recommend_candidate.py       # Top-N, deadline, cancellation, select(), one log line
      infrastructure/                  # The only place anthropic, fastembed and pgvector live.
        llm/
          anthropic_errors.py          # Shared transient-vs-configuration classification
          anthropic_llm_client.py      # Timeout, retries, error classification
          claude_candidate_assessor.py # Rubric via structured output; 3 samples; per-call concurrency limit
        agent/
          anthropic_agent_model.py     # One messages.create per turn; keeps every content block
          langgraph_catalog_agent.py   # Graph: model → tools → model, RAG answer past the limit
          tools.py                     # Tool definitions, dispatch, question embedded once per run
        embeddings/
          fastembed_embedding_client.py
        persistence/
          models.py                    # ProductDocumentModel (vector(384), HNSW, unique sku)
          sqlalchemy_document_index.py
          sqlalchemy_document_search.py
        catalog/
          list_products_catalog_reader.py  # The only adapter that talks to catalog
      ui/
        schemas.py                     # AskRequest, AnswerResponse, SourceResponse
        routers/assistant.py           # POST /assistant/ask
        cli/reindex.py                 # make reindex → python -m contexts.assistant.ui.cli.reindex
        dependencies.py                # Per-context DI wiring (shared by API and CLI)
  shared/                              # Cross-cutting only. Keep it small.
    domain/
      errors.py                        # DomainError + NotFound / Conflict / InvalidInput / ServiceUnavailable
    infrastructure/
      settings.py                      # Pydantic BaseSettings (DB + LLM + embeddings)
      database.py                      # async engine + session factory + get_session dep
      db_base.py                       # SQLAlchemy declarative Base
      exception_handlers.py            # Domain errors → 404 / 409 / 422 / 503
alembic/
  env.py                               # Async, reads URL from settings
  script.py.mako                       # Migration template (Python 3.10 unions)
  versions/                            # Generated migration files
alembic.ini
tests/
  conftest.py                          # make_product, db_engine, db_session, client (sync)
  fakes/                               # Port-boundary fakes shared by suites (LLM, embeddings, documents)
  unit/                                # Pure logic. No I/O.
  integration/                         # Real adapters: postgres + pgvector, Anthropic client on a mocked transport.
  e2e/                                 # AsyncClient + ASGITransport against the full app.
main.py                                # create_app() — composes routers + handlers
docker-compose.yml                     # api + db + db-test (pgvector images; db-test on tmpfs)
Dockerfile
Makefile
```

When a layer's single file grows or a second concept ships, that file gets promoted to a directory (e.g. `domain/product.py` → `domain/product/{entity.py,value_objects.py}`). Don't introduce the directory speculatively.

---

## Quick Start

**Prerequisites:** Docker + Docker Compose. Everything (deps, server, tests, linters) runs inside containers — no local Python install required.

```bash
cp .env.example .env    # then set ANTHROPIC_API_KEY to use the assistant

make install            # Build the docker image (installs deps inside)
make migrate            # Apply migrations to the dev database
make migrate-test       # Apply migrations to the test database (required before make test)
make reindex            # Index catalog products for the assistant (incremental)
make run                # Start dev server in the foreground (uvicorn --reload)
make up                 # Same, in the background
make down               # Stop and remove containers

make test               # Full test suite (never calls a real model)
make unit-test          # Unit tests only (no I/O)
make integration-test   # Integration tests (real postgres, mocked LLM transport)
make e2e-test           # E2E tests (HTTP via TestClient/AsyncClient)
make eval               # Evals E1–E4 against the real Claude API (reads the key from .env; costs money)
make lint               # ruff + pylint + mypy
make format             # auto-format
make sh                 # Shell into a fresh api container

make migration m="add foo"  # Generate a new Alembic migration via autogenerate
```

LLM settings (all in `.env.example`): `ANTHROPIC_API_KEY`, `LLM_MODEL` (default `claude-haiku-5-5`), `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`, `LLM_MAX_TOKENS`. Retrieval: `EMBEDDING_MODEL` (default `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) and `RAG_TOP_K` (default 5, max 40). The embedding model (~0.24 GB) is **baked into the Docker image at build time**; at runtime it is only loaded from disk (`EMBEDDING_LOCAL_FILES_ONLY=true`, never downloaded) and warmed up when the app starts, so computing embeddings needs no network (the LLM call still does).

Assistant mode: `ASSISTANT_MODE` (`rag` by default, or `agent`) and `AGENT_MAX_TOOL_CALLS` (default 5). Candidate selector: `SELECTOR_TOP_N` (10), `SELECTOR_SAMPLES` (3), `SELECTOR_MAX_CONCURRENCY` (10), `SELECTOR_TIMEOUT_S` (10), `SELECTOR_MAX_TOKENS` (1024), `SELECTOR_REQUIREMENTS_THRESHOLD` (0.5) and `SELECTOR_MIN_SCORE` (0.5).

API is served on `http://localhost:8000` with auto-generated docs:

- `/docs` — Swagger UI (interactive)
- `/redoc` — [ReDoc](https://github.com/Rebilly/ReDoc) (alternative reference UI)
- `/openapi.json` — raw OpenAPI schema (importable into Postman, OpenAPI generators, etc.)

---

## Testing

| Suite        | Location               | What it covers                                              |
|--------------|------------------------|-------------------------------------------------------------|
| Unit         | `tests/unit/`          | Pure domain and application logic. Mocks at the port boundary via `FakeProductRepository`, `FakeLLMClient`, `FakeEmbeddingClient`, `FakeDocumentIndex` and `FakeDocumentSearch`. Covers incremental indexing and orphan deletion. **No I/O.** |
| Integration  | `tests/integration/`   | Real `SqlAlchemyProductRepository` against `db-test` (transaction-rollback per test). Real `AnthropicLLMClient` on an `httpx2.MockTransport`: error classification and retry bound. Real pgvector adapters: upsert, hashes, delete, nearest-first search. Catalog reader across pages. |
| E2E          | `tests/e2e/`           | Full HTTP via `httpx.AsyncClient` + `ASGITransport`. The DB session, `LLMClient`, `EmbeddingClient` and `DocumentSearch` are overridden; covers sources, fallback and that no indexing endpoint exists. Each domain error is checked against its status code. In agent mode the agent is a `FakeCatalogAgent`, and `rag` mode is checked never to build the agent. |
| Evals        | `tests/evals/`         | Opt-in (`eval` marker, `make eval`), against the real Claude API. E1: selector accuracy; E2: same outcome with shuffled candidates; E3: same outcome on a rerun; E4: full agent end to end. The scoring rule's own tests are not marked and run in `make test`. |

---
