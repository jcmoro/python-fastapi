# python-fastapi

A reference Python **FastAPI** project demonstrating clean, scalable, and maintainable architecture using **Domain-Driven Design (DDD)** and the **Hexagonal (Ports & Adapters)** pattern.

The repo is intentionally small and opinionated: business logic stays pure, frameworks live at the edges, and every bounded context is a vertical slice with strict layering.

---

## Goals

- Keep **business logic pure** and isolated from frameworks.
- Make **bounded contexts** the unit of feature ownership.
- Validate everything at the boundary with **Pydantic v2**.
- Stay simple: **no abstraction without a present need**.

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

## Conventions

- `snake_case` for modules/functions/variables; `PascalCase` for classes; `*DTO` suffix for data transfer objects.
- Type hints required; **avoid `Any`**.
- Domain layer must never import infrastructure or framework code.
- DTOs are **data-only** and immutable where possible.
- Use `ORJSONResponse` (powered by `orjson`) as the FastAPI `default_response_class`.
- Endpoints must declare `summary`, `description`, `response_model`, `status_code`, and `tags`.
- Annotate every Pydantic field with `Field(..., description=..., examples=[...])` so OpenAPI is self-documenting.
- Configuration only via `BaseSettings`; never read `os.environ` directly outside `shared/infrastructure/settings`.
- Async where I/O happens; sync where CPU work happens. Don't block the event loop.
- Atomic, minimal PRs. Lint and tests must pass before opening.

---

## Testing

| Suite        | Location               | What it covers                                              |
|--------------|------------------------|-------------------------------------------------------------|
| Unit         | `tests/unit/`          | Pure domain and application logic. **No I/O.**              |
| Integration  | `tests/integration/`   | Real adapters (DB, HTTP) against ephemeral services.        |
| E2E          | `tests/e2e/`           | FastAPI `TestClient` exercising the full app.               |

Each use case must include **at least one unit test**. Tests validate behavior, not implementation details.

---

## API Documentation

This project treats OpenAPI as a first-class deliverable:

- App-level `title`, `description`, `version`, `contact`, and `license_info` are set on the `FastAPI` instance.
- Long endpoint descriptions live in `docs/api_docs/<method>_<path>.md` and are loaded via `Path().read_text()` into the route's `description`.
- Error responses are documented per route via the `responses=` parameter.
- Pydantic v2 `Field(examples=[...])` drives the request/response examples.

---

## References

- [FastAPI + DDD](https://medium.com/p/3b92be4e436c)
- [FastAPI in Production: 7 Mistakes That Will Destroy Your App](https://medium.com/@inprogrammer/fastapi-in-production-7-mistakes-that-will-destroy-your-app-ea42b4bf2c54)
- [How to Document an API for Python FastAPI](https://medium.com/codex/how-to-document-an-api-for-python-fastapi-best-practices-for-maintainable-and-readable-code-a183a3f7f036)

---

## License

TBD
