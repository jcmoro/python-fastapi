# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Context Priority

When rules conflict, prioritize in this order:

1. Non-Negotiable Rules
2. Execution Protocol
3. Self-Verification
4. Quality Gates
5. Remaining documentation

Explicit user instructions always override this file.

---

## Project Overview

A reference Python FastAPI project built around **Domain-Driven Design (DDD)** and **Hexagonal (Ports & Adapters)** architecture. Goals: clean, scalable, maintainable; pure business logic; frameworks at the edges; bounded contexts as vertical slices.

See `README.md` for stack, layout, and quick-start commands. This file describes how to *operate* in the repo.

### Bounded Contexts

Each bounded context lives at `src/contexts/<context_name>/` and is composed of four layers (innermost first):

| Layer            | May depend on                         | Contains                                                            |
|------------------|---------------------------------------|---------------------------------------------------------------------|
| `domain/`        | nothing                               | Entities, value objects, domain services, **port** interfaces       |
| `application/`   | `domain/`                             | Use cases (commands/queries), DTOs, application services            |
| `infrastructure/`| `domain/`, `application/`             | Adapter implementations of ports (DB, HTTP, message brokers)        |
| `ui/`            | `application/` + DTOs                 | FastAPI routers, Pydantic schemas, context-scoped DI                |

Cross-context contracts travel as **DTOs only**. No shared domain models between contexts.

`src/shared/` holds cross-cutting infrastructure (settings, logging, errors, db engine, http client) and a *small* shared kernel — use it sparingly and only for primitives that genuinely have no owner.

---

## Commands

**Everything runs inside Docker.** Do not assume a local Python interpreter; use `make` targets, which delegate to `docker compose`. This keeps dev parity with CI and prod.

| Command           | Purpose                                       |
|-------------------|-----------------------------------------------|
| `make install`    | Install dependencies (editable + dev)         |
| `make run`        | Start dev server (`uvicorn --reload`)         |
| `make test`       | Run full test suite                           |
| `make unit-test`  | Run unit tests only                           |
| `make lint`       | `pylint` + `ruff` + `mypy`                    |
| `make format`     | Auto-format the codebase                      |
| `make up` / `down`| `docker-compose` lifecycle                    |

Run a single test:

```bash
pytest tests/unit/contexts/<context>/application/test_<use_case>.py::test_<name> -q
```

---

## Architecture

### Data Flow

```
HTTP request
  → ui/routers (FastAPI)            # validation via Pydantic schemas
  → ui translates schema → DTO
  → application/<use_case>          # orchestrates domain
  → domain/* (pure)                 # entities, value objects, services
  → application calls a port (interface)
  → infrastructure/* adapter        # concrete impl injected via FastAPI DI
  → application returns DTO
  → ui translates DTO → response schema
HTTP response
```

Dependencies always point **inward**. The domain never imports framework, ORM, or HTTP code.

### Key Patterns

- **Use cases as first-class objects.** Each command/query is a small class or function in `application/`. Routers do not contain business logic; they map HTTP to a use case.
- **Ports & Adapters.** Repositories and external services are defined as ABCs in `domain/ports/` and implemented in `infrastructure/`. Wiring lives in `ui/dependencies.py` (per-context) or `shared/infrastructure/` for cross-cutting deps.
- **Pydantic v2 at the boundary.** All HTTP input/output is a Pydantic model with `Field(..., description=..., examples=[...])`. Internal layers exchange DTOs (plain dataclasses or Pydantic models marked `frozen=True`).
- **Settings via `BaseSettings`.** Never read `os.environ` directly outside `shared/infrastructure/settings`.
- **Errors.** Domain raises domain exceptions; a single `shared/infrastructure/exception_handlers.py` maps them to HTTP responses. Routers do not raise `HTTPException` directly for domain failures.
- **Async vs. sync.** Async where I/O happens (DB drivers that support it, HTTP clients). Sync (or `run_in_threadpool`) for CPU work. Never block the event loop.

---

## Conventions

- Python ≥ 3.10, type hints required, **avoid `Any`**.
- `snake_case` modules/functions/variables, `PascalCase` classes, `*DTO` suffix for data transfer objects.
- DTOs are data-only (no business logic), immutable where possible.
- JSON serialization is FastAPI's native path (Pydantic core). `ORJSONResponse` was removed in favour of the framework default once FastAPI 0.130+ deprecated it.
- Routers are thin: validate input, call a use case, return a response model. **No domain logic in router files.**
- No shared domain models between bounded contexts; use DTOs for cross-context contracts.
- Every endpoint declares: `summary`, `description`, `response_model`, `status_code`, `tags`, and a `responses=` map for documented errors.
- **Docstrings are allowed in exactly two places. Nowhere else.**
  - **Ports** (`domain/ports/`), for the behaviour the types do not express: which exceptions are raised and when, and which invariants or time bounds are guaranteed.
  - **Whatever ends up in OpenAPI**: route `summary` / `description`, `Field(description=..., examples=[...])`, and Pydantic model docstrings that become schema descriptions.
- Atomic, minimal PRs. `make lint` and `make test` must pass before opening.

---

## Non-Negotiable Rules

* Respect bounded context boundaries
* No cross-context shortcuts
* Domain layer has **zero** infrastructure/framework dependencies
* UI layer contains **no** business logic
* Repositories accessed only from Application or Infrastructure
* Prefer consistency over novelty
* Changes must be minimal and focused

---

## Approach (Agent Operating Rules)

* Understand context before making changes.
* Inspect relevant existing files first.
* Prefer minimal edits over rewriting files.
* Re-check files before modifying if context may have changed.
* Follow existing architectural patterns.
* Keep solutions simple and explicit.
* Provide concise, implementation-focused responses.
* Do not expose internal reasoning unless explicitly requested.
* Avoid conversational filler.

---

## Execution Protocol (Mandatory)

Follow this sequence for every task:

### 1. Understand

* Identify bounded context
* Identify affected layer(s)
* Read relevant files
* Confirm architectural constraints

### 2. Plan

* Determine minimal required changes
* Extend existing patterns
* Identify required tests and contract impact

### 3. Implement

* Apply focused modifications
* Respect layer boundaries
* Prefer editing existing code

### 4. Validate

* Ensure quality gates pass
* Confirm architecture rules remain satisfied

### 5. Deliver

* Provide concise summary of changes
* Avoid unnecessary explanations

---

## Planning Constraints

* Do not implement before understanding existing patterns.
* Assume repository already contains the correct architectural solution.
* Prefer consistency over introducing new abstractions.

---

## Self-Verification (Mandatory Before Delivering)

Before considering work complete, verify:

### Architecture

* No layer violations (check imports — domain has zero framework imports)
* No cross-context dependency introduced
* Domain remains infrastructure-free

### Code Quality

* Matches patterns already used in the context
* No unnecessary abstractions
* Minimal modification surface

### Contracts

* DTOs consistent with Pydantic schemas at the boundary
* OpenAPI reflects new/changed endpoints (summary, description, response_model, error responses)

### Testing

* Required unit or functional tests exist
* Tests validate behavior, not implementation details

If any rule fails → revise before delivering.

---

## Overengineering Guard

Reject solutions that:

* Introduce new architectural patterns without precedent
* Add abstractions not required by the task
* Modify multiple bounded contexts unnecessarily
* Replace working implementations without explicit reason

---

## Testing Strategy

| Suite        | Location               | Scope                                                        |
|--------------|------------------------|--------------------------------------------------------------|
| Unit         | `tests/unit/`          | Pure domain and application logic. **No I/O.**               |
| Integration  | `tests/integration/`   | Real adapters (DB, HTTP) against ephemeral services.         |
| E2E          | `tests/e2e/`           | FastAPI `TestClient` exercising the full app.                |

* Each use case must include ≥1 unit test.
* Tests validate **behavior**, not implementation details.
* Mock at the **port boundary**, never inside the domain.

---

## Quality Gates (Required Before Completion)

All must be green:

1. `make unit-test`
2. `make lint` (pylint + ruff + mypy clean)

Work is not complete until all gates pass.

---

## Communication Rules

* Assume reader understands DDD and Hexagonal architecture.
* Do not explain architecture unless requested.
* Focus on implementation and correctness.
* Keep responses concise and technical.

---

## References

- [FastAPI + DDD](https://medium.com/p/3b92be4e436c)
- [FastAPI in Production: 7 Mistakes That Will Destroy Your App](https://medium.com/@inprogrammer/fastapi-in-production-7-mistakes-that-will-destroy-your-app-ea42b4bf2c54)
- [How to Document an API for Python FastAPI](https://medium.com/codex/how-to-document-an-api-for-python-fastapi-best-practices-for-maintainable-and-readable-code-a183a3f7f036)
- See `README.md` for stack, project layout, and developer commands.
