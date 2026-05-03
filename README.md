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
| Serialization    | FastAPI native (Pydantic core)        |
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

The current shape (`catalog` is the only context so far). Subdirectories are introduced only when they earn their place — single-file modules are preferred for the first occupant of each layer.

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
  shared/                              # Cross-cutting only. Keep it small.
    domain/
      errors.py                        # DomainError + NotFoundError / ConflictError / InvalidInputError
    infrastructure/
      settings.py                      # Pydantic BaseSettings
      database.py                      # async engine + session factory + get_session dep
      db_base.py                       # SQLAlchemy declarative Base
      exception_handlers.py            # Domain errors → HTTP responses
alembic/
  env.py                               # Async, reads URL from settings
  script.py.mako                       # Migration template (Python 3.10 unions)
  versions/                            # Generated migration files
alembic.ini
tests/
  conftest.py                          # make_product, db_engine, db_session, client (sync)
  unit/                                # Pure logic. No I/O.
  integration/                         # Real postgres, transaction-rollback isolation.
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
cp .env.example .env

make install            # Build the docker image (installs deps inside)
make migrate            # Apply migrations to the dev database
make migrate-test       # Apply migrations to the test database (required before make test)
make run                # Start dev server in the foreground (uvicorn --reload)
make up                 # Same, in the background
make down               # Stop and remove containers

make test               # Full test suite
make unit-test          # Unit tests only (no I/O)
make integration-test   # Integration tests (real postgres)
make e2e-test           # E2E tests (HTTP via TestClient/AsyncClient)
make lint               # ruff + pylint + mypy
make format             # auto-format
make sh                 # Shell into a fresh api container

make migration m="add foo"  # Generate a new Alembic migration via autogenerate
```

API is served on `http://localhost:8000` with auto-generated docs:

- `/docs` — Swagger UI (interactive)
- `/redoc` — [ReDoc](https://github.com/Rebilly/ReDoc) (alternative reference UI)
- `/openapi.json` — raw OpenAPI schema (importable into Postman, OpenAPI generators, etc.)

---

## Testing

| Suite        | Location               | What it covers                                              |
|--------------|------------------------|-------------------------------------------------------------|
| Unit         | `tests/unit/`          | Pure domain and application logic. Mocks at the port boundary via `FakeProductRepository`. **No I/O.** |
| Integration  | `tests/integration/`   | Real `SqlAlchemyProductRepository` against `db-test`. Transaction-rollback per test for isolation. |
| E2E          | `tests/e2e/`           | Full HTTP via `httpx.AsyncClient` + `ASGITransport`. App's `get_session` is overridden to share the test transaction. |

---
