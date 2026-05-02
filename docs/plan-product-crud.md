# Plan — Catalog: Product CRUD + Test Fixtures

Bounded context: `catalog`. Architecture: DDD + Hexagonal (per `CLAUDE.md`).

## Decisions taken

- **Persistence**: PostgreSQL via SQLAlchemy 2.0 async + `asyncpg`. No in-memory production adapter.
- **Test fixtures**: `make_product`, `add_product`, `seeded_products` all in scope.
- **Identifier**: server-generated `UUID4` returned in responses.
- **Money**: single currency field (`EUR` default) + integer `price_cents` to avoid float drift. Keep it simple; promote to a `Money` VO only if a second currency appears.

## Still open (need confirmation)

- **Schema management**: Alembic from day one (canonical, prod-ready) vs. `Base.metadata.create_all` on startup (faster, fine until first prod schema change). _Recommendation_: Alembic.
- **Test database**: dedicated `postgres-test` service in `docker-compose.yml` reused across runs (fast, simple) vs. `testcontainers-python` spinning a fresh container per session (isolated, slower, extra dep). _Recommendation_: dedicated service for now; testcontainers when CI requires full isolation.
- **Unit tests**: still mock the `ProductRepository` port — they do not touch postgres. Only integration and e2e exercise the real adapter.

## Scope

A minimal `Product` aggregate with full CRUD reachable via HTTP, plus reusable pytest fixtures to seed products in tests.

Endpoints (all under `/products`, tag `catalog`):

| Method | Path              | Use case          | Status |
|--------|-------------------|-------------------|--------|
| POST   | `/products`       | `CreateProduct`   | 201    |
| GET    | `/products/{id}`  | `GetProduct`      | 200    |
| GET    | `/products`       | `ListProducts`    | 200    |
| PATCH  | `/products/{id}`  | `UpdateProduct`   | 200    |
| DELETE | `/products/{id}`  | `DeleteProduct`   | 204    |

## Layered breakdown

### Domain — `src/contexts/catalog/domain/`

- `product.py` — `Product` entity (`id: UUID`, `sku: str`, `name: str`, `price_cents: int`, `currency: str`, `created_at: datetime`).
- `exceptions.py` — `ProductNotFound`, `DuplicateSku`, `InvalidProduct`.
- `ports/product_repository.py` — `ProductRepository` ABC: `add`, `get`, `list`, `update`, `delete`, `exists_sku`.

No framework imports. Pure Python + stdlib.

### Application — `src/contexts/catalog/application/`

- `dtos.py` — `ProductDTO`, `CreateProductCommand`, `UpdateProductCommand` (frozen Pydantic models or dataclasses).
- `use_cases/create_product.py` — validates SKU uniqueness, builds entity, persists, returns DTO.
- `use_cases/get_product.py`
- `use_cases/list_product.py` — supports basic pagination (`limit`, `offset`).
- `use_cases/update_product.py` — partial update.
- `use_cases/delete_product.py`

Each use case is a small class with `__init__(repo: ProductRepository)` and an async `execute(...)` method.

### Infrastructure — `src/contexts/catalog/infrastructure/`

- `persistence/models.py` — SQLAlchemy ORM model `ProductModel` (table `products`).
- `persistence/mappers.py` — `to_domain` / `to_model` translators.
- `persistence/sqlalchemy_product_repository.py` — async adapter implementing `ProductRepository`. Uses `AsyncSession`.
- `persistence/in_memory_product_repository.py` — used **only** by unit tests for the use-case suites that need a real port (most use mocks). Kept tiny.

### UI — `src/contexts/catalog/ui/`

- `schemas.py` — Pydantic v2: `ProductCreate`, `ProductUpdate`, `ProductResponse` with `Field(..., description=..., examples=[...])`.
- `routers/products.py` — thin router; one function per endpoint, each calls a use case and maps DTO → response schema.
- `dependencies.py` — `get_product_repository()` provider (singleton in-memory for dev). FastAPI `Depends` wires use cases.

Register the router in `main.py` via `application.include_router(products_router)`.

### Shared — `src/shared/infrastructure/`

- `database.py` — async engine + `async_sessionmaker` built from `Settings.database_url`. Exposes `get_session()` dep.
- `db_base.py` — declarative `Base` for ORM models.
- `exception_handlers.py` — maps domain exceptions to HTTP responses:
  - `ProductNotFound` → 404
  - `DuplicateSku` → 409
  - `InvalidProduct` → 422

Wired in `main.py` with `application.add_exception_handler(...)`.

### Settings — `src/shared/infrastructure/settings.py`

- Add `database_url: PostgresDsn` (env: `DATABASE_URL`).
- Default for local dev composed from `POSTGRES_USER/PASSWORD/HOST/PORT/DB` envs in `docker-compose.yml`.

## Tests

### Fixtures

`tests/conftest.py` (root) — shared fixtures:

- `make_product` — pure factory: `make_product(sku="SKU-1", name=..., price_cents=1000) -> Product`. Builds valid domain entities, no persistence. Auto-increments SKU on each call to avoid collisions.

`tests/integration/conftest.py` and `tests/e2e/conftest.py` — DB-bound fixtures:

- `db_engine` (session-scoped) — async engine pointing at the test DB.
- `db_session` (function-scoped) — opens a transaction, yields a session, rolls back on teardown to keep tests isolated.
- `product_repository` — `SqlAlchemyProductRepository(db_session)`.
- `app` — FastAPI app with `get_session` overridden to yield the test session.
- `client` — `TestClient` against the overridden app.
- `add_product` — async factory persisting via `product_repository` and returning the saved `Product`. Accepts kwargs.
- `seeded_products` — yields N persisted products for list/pagination tests (default N=5).

Unit tests under `tests/unit/` do **not** import these DB fixtures — they mock the port.

### Test layout

- `tests/unit/contexts/catalog/application/` — one test file per use case, mocking `ProductRepository`.
- `tests/unit/contexts/catalog/domain/` — entity/VO invariants.
- `tests/integration/contexts/catalog/infrastructure/` — exercise the in-memory repo against the port contract (later: same suite against SQLAlchemy).
- `tests/e2e/test_products.py` — happy path + 404/409/422 via `TestClient`.

## Quality gates

- `make unit-test` green.
- `make lint` green (ruff + pylint + mypy strict).
- E2E covers create → get → list → update → delete.

## Execution order

1. Infra prerequisites: add `asyncpg` + `alembic` to deps, postgres service in `docker-compose.yml` (app + db + db-test), `database.py`, `db_base.py`, settings.
2. Alembic init + first migration scaffolding (empty).
3. Domain layer: `Product` entity, exceptions, `ProductRepository` port.
4. Application: DTOs + `CreateProduct` use case + unit test (mocked port).
5. Infrastructure: ORM model + mapper + `SqlAlchemyProductRepository`.
6. Alembic migration: create `products` table.
7. UI: schemas + create/get router + DI wiring.
8. Exception handlers + register router in `main.py`.
9. Remaining use cases (list, update, delete) + unit tests.
10. Test fixtures (`make_product`, `db_session`, `product_repository`, `add_product`, `seeded_products`).
11. Integration tests (port contract against real postgres).
12. E2E tests (full HTTP).
13. Quality gates: `make unit-test`, `make test`, `make lint`.

## Out of scope

- Authentication/authorization.
- Search/filtering beyond pagination.
- Soft deletes / audit log.
- Cross-context events (no other context exists yet).
- Connection pooling tuning beyond SQLAlchemy defaults.
- Read replicas / multi-tenant.
