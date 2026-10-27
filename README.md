<div align="center">

# python-fastapi

**Generative AI on FastAPI, done the clean way.**

A reference **Generative AI backend** in Python: an LLM-powered assistant over a product catalog, built with **FastAPI**, **Domain-Driven Design (DDD)** and the **Hexagonal (Ports & Adapters)** pattern. The model is an adapter behind a port — swap providers, fake it in tests, and keep it out of your domain.

[![CI](https://github.com/jcmoro/python-fastapi/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jcmoro/python-fastapi/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-99%20passing-2e7d32?style=flat)
![Architecture](https://img.shields.io/badge/architecture-DDD%20%2B%20Hexagonal-2e7d32?style=flat)
![mypy](https://img.shields.io/badge/mypy-strict-1565c0?style=flat)
![GenAI](https://img.shields.io/badge/GenAI-LLM%20assistant-6a1b9a?style=flat)
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
- **Tests never call a real model.** Unit and e2e tests use `FakeLLMClient` at the port boundary. The real adapter is tested against a mocked HTTP transport — no network, no cost.
- **Failures have a contract.** Transient LLM failures (connection, timeout, 429, 5xx) return **503**. Configuration errors (bad key, unknown model) are not disguised as outages.
- **Latency is bounded.** `LLM_TIMEOUT_S` applies per attempt and `LLM_MAX_RETRIES` defaults to 0, so the worst case is `timeout * (retries + 1)`.
- **Every answer reports its cost.** Responses include the model used, input/output tokens and latency.

---

## What works today

`POST /assistant/ask` — ask a natural-language question and get the model's answer plus usage.

```bash
curl -s -X POST http://localhost:8000/assistant/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "Which widgets cost less than 20 EUR?"}'
```

Example response (values are illustrative):

```json
{
  "text": "…",
  "usage": {
    "model": "claude-haiku-5-5",
    "input_tokens": 52,
    "output_tokens": 87,
    "latency_ms": 1240
  }
}
```

| Status | When |
|--------|------|
| `200`  | The model answered. |
| `422`  | Empty or blank question, more than 1,000 characters, or unknown fields. |
| `503`  | The LLM is unavailable: connection error, timeout, rate limit (429) or server error (5xx). |
| `500`  | Misconfiguration: missing or invalid API key, unknown model, invalid request. |

The assistant does not read the catalog yet — that is what RAG (next on the roadmap) adds.

---

## Roadmap

Delivered as small, shippable PRs. Full plan: [`docs/plan-assistant-genai.md`](docs/plan-assistant-genai.md).

| Step | Scope | Status |
|------|-------|--------|
| 1 | `LLMClient` port, Anthropic adapter, `POST /assistant/ask`, failure contract | ✅ Done |
| 2 | **RAG** with `pgvector` in the existing Postgres: embeddings behind a port, top-k retrieval, `sources` in the answer, deterministic fallback when the LLM fails | ⏳ Planned |
| 3 | **Agent** with LangGraph: catalog tools, step limits, token usage summed across steps, offline evals | ⏳ Planned |
| 4 | **Deploy**: Kubernetes manifests, local `kind` cluster, optional cloud target | ⏳ Planned |

---

## Stack

| Layer            | Choice                                                   |
|------------------|----------------------------------------------------------|
| Language         | Python ≥ 3.10 (type hints required)                      |
| Web framework    | FastAPI + Uvicorn                                        |
| LLM              | Anthropic Claude (`anthropic` SDK), behind `LLMClient`   |
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

Cross-context contracts travel as **DTOs only** — no shared domain models between bounded contexts. `assistant` never imports `catalog`.

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
        exceptions.py                  # InvalidQuestionError, LLMUnavailableError
        ports/
          llm_client.py                # LLMClient ABC — documents which failures it raises
      application/
        dtos.py                        # AskCommand, AnswerDTO, UsageDTO
        use_cases/
          ask_assistant.py
      infrastructure/                  # The only place the anthropic SDK lives.
        llm/
          anthropic_llm_client.py      # Timeout, retries, error classification
      ui/
        schemas.py                     # AskRequest, AnswerResponse
        routers/assistant.py           # POST /assistant/ask
        dependencies.py                # Per-context DI wiring
  shared/                              # Cross-cutting only. Keep it small.
    domain/
      errors.py                        # DomainError + NotFound / Conflict / InvalidInput / ServiceUnavailable
    infrastructure/
      settings.py                      # Pydantic BaseSettings (DB + LLM)
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
  fakes/                               # Port-boundary fakes shared by suites (FakeLLMClient)
  unit/                                # Pure logic. No I/O.
  integration/                         # Real adapters: postgres, Anthropic client on a mocked transport.
  e2e/                                 # AsyncClient + ASGITransport against the full app.
main.py                                # create_app() — composes routers + handlers
docker-compose.yml                     # api + db + db-test (db-test on tmpfs)
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
make run                # Start dev server in the foreground (uvicorn --reload)
make up                 # Same, in the background
make down               # Stop and remove containers

make test               # Full test suite (never calls a real model)
make unit-test          # Unit tests only (no I/O)
make integration-test   # Integration tests (real postgres, mocked LLM transport)
make e2e-test           # E2E tests (HTTP via TestClient/AsyncClient)
make lint               # ruff + pylint + mypy
make format             # auto-format
make sh                 # Shell into a fresh api container

make migration m="add foo"  # Generate a new Alembic migration via autogenerate
```

LLM settings (all in `.env.example`): `ANTHROPIC_API_KEY`, `LLM_MODEL` (default `claude-haiku-5-5`), `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`, `LLM_MAX_TOKENS`.

API is served on `http://localhost:8000` with auto-generated docs:

- `/docs` — Swagger UI (interactive)
- `/redoc` — [ReDoc](https://github.com/Rebilly/ReDoc) (alternative reference UI)
- `/openapi.json` — raw OpenAPI schema (importable into Postman, OpenAPI generators, etc.)

---

## Testing

| Suite        | Location               | What it covers                                              |
|--------------|------------------------|-------------------------------------------------------------|
| Unit         | `tests/unit/`          | Pure domain and application logic. Mocks at the port boundary via `FakeProductRepository` and `FakeLLMClient`. **No I/O.** |
| Integration  | `tests/integration/`   | Real `SqlAlchemyProductRepository` against `db-test` (transaction-rollback per test). Real `AnthropicLLMClient` on an `httpx2.MockTransport`: error classification and retry bound. |
| E2E          | `tests/e2e/`           | Full HTTP via `httpx.AsyncClient` + `ASGITransport`. The DB session and the `LLMClient` are overridden; each domain error is checked against its status code. |

---
