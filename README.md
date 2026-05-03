# python-fastapi

A reference Python **FastAPI** project demonstrating clean, scalable, and maintainable architecture using **Domain-Driven Design (DDD)** and the **Hexagonal (Ports & Adapters)** pattern.

---

## Stack

| Layer            | Choice                                |
|------------------|---------------------------------------|
| Language         | Python ≥ 3.10 (type hints required)   |
| Web framework    | FastAPI + Uvicorn                     |
| Validation       | Pydantic v2                           |
| Settings         | `pydantic-settings` (`BaseSettings`)  |
| Serialization    | `orjson` (via `ORJSONResponse`)       |
| Tests            | `pytest`, `pytest-asyncio`, `httpx`   |
| Static checks    | `pylint`, `ruff`, `mypy`              |
| Packaging        | `pyproject.toml`                      |
| Container / CLI  | Docker + `make`                       |

---

## Architecture

DDD + Hexagonal. Each **bounded context** is a vertical slice with four layers:

| Layer            | Allowed dependencies                | Responsibility                                                       |
|------------------|-------------------------------------|----------------------------------------------------------------------|
| `domain/`        | none                                | Entities, value objects, domain services, **port** interfaces.       |
| `application/`   | `domain/`                           | Use cases (commands and queries), DTOs, application services.        |
| `infrastructure/`| `domain/`, `application/`           | Adapter implementations (repositories, HTTP clients, persistence).   |
| `ui/`            | `application/`, DTOs                | FastAPI routers and Pydantic schemas. Translates HTTP ↔ use cases.   |

**Direction of dependencies points inward.** Outer layers depend on inner ones, never the reverse.

Cross-context contracts travel as **DTOs only** — no shared domain models between bounded contexts.

### Project Layout

```
src/
  contexts/
    <context_name>/
      domain/
        entities/
        value_objects/
        ports/             # Repository / service interfaces
      application/
        commands/          # Write use cases
        queries/           # Read use cases
        dtos/
      infrastructure/
        persistence/       # Adapter implementations of ports
        http/
      ui/
        routers/           # FastAPI APIRouter modules
        schemas/           # Pydantic request/response models
        dependencies.py    # Context-scoped DI wiring
  shared/
    domain/                # Shared kernel (use sparingly)
    infrastructure/        # Settings, logging, db, http client, errors
tests/
  unit/
  integration/
  e2e/
main.py                    # Composes routers, builds the FastAPI app
```

---

## Quick Start

**Prerequisites:** Docker + Docker Compose. Everything (deps, server, tests, linters) runs inside containers — no local Python install required.

```bash
cp .env.example .env

make install      # Build the docker image (installs deps inside)
make run          # Start dev server in the foreground (uvicorn --reload)
make up           # Same, in the background
make down         # Stop and remove containers

make test         # Full test suite (in container)
make unit-test    # Unit tests only
make lint         # ruff + pylint + mypy
make format       # auto-format
make sh           # Shell into the running api container
```

API is served on `http://localhost:8000` with auto-generated docs:

- `/docs` — Swagger UI (interactive)
- `/redoc` — [ReDoc](https://github.com/Rebilly/ReDoc) (alternative reference UI)
- `/openapi.json` — raw OpenAPI schema (importable into Postman, OpenAPI generators, etc.)

---

## Testing

| Suite        | Location               | What it covers                                              |
|--------------|------------------------|-------------------------------------------------------------|
| Unit         | `tests/unit/`          | Pure domain and application logic. **No I/O.**              |
| Integration  | `tests/integration/`   | Real adapters (DB, HTTP) against ephemeral services.        |
| E2E          | `tests/e2e/`           | FastAPI `TestClient` exercising the full app.               |

---
