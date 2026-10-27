# Paso 14 — Contexto `assistant`: puerto `LLMClient` + `POST /assistant/ask` (PR 1)

Primer PR del plan `docs/plan-assistant-genai.md`. Rama `feature/assistant-llm-port`.

## Qué

Un endpoint `POST /assistant/ask` que recibe una pregunta en lenguaje natural y devuelve la
respuesta de un LLM (Claude) junto con el uso de tokens y la latencia. El LLM vive detrás de un
puerto (`LLMClient`); el dominio no importa `anthropic`.

## Por qué

Es la base de los PR siguientes (RAG, agente). Fija desde el principio que el proveedor de LLM es
un adaptador intercambiable, que los tests nunca llaman a un modelo real y que los fallos del LLM
tienen un contrato HTTP explícito.

## Criterios de aceptación

| Criterio | Cómo se demuestra |
|---|---|
| 200 con `text` y `usage` (`model`, `input_tokens`, `output_tokens`, `latency_ms`) | `tests/e2e/test_assistant.py::TestAsk::test_returns_200_with_answer_and_usage` |
| 422 si la pregunta está vacía, en blanco, supera 1000 caracteres o trae campos extra | `tests/unit/.../test_question.py`, `tests/e2e/test_assistant.py` (422) |
| 503 si el LLM no está disponible (conexión, timeout, 429, 5xx) | `tests/integration/.../test_anthropic_llm_client.py`, `tests/e2e/test_assistant.py` (503) |
| Errores de configuración (400/401/403/404) **no** se disfrazan de 503 | `test_configuration_error_propagates[...]` |
| `LLM_TIMEOUT_S` acota de verdad el tiempo de pared (sin reintentos ocultos) | `TestTimeoutBound::test_timing_out_upstream_is_attempted_once` |
| Cada error de dominio compartido mapea a su código HTTP | `tests/e2e/test_exception_handlers.py` |
| El dominio no depende de frameworks ni de otros contextos | `grep` de imports (ver Verificación) |

## Decisiones y porqué

### 1. 503 en el PR 1; el fallback con top-k se mueve al PR 2

El plan recomendaba un fallback determinista (resultados top-k sin generación). En el PR 1 no hay
recuperación, así que ese fallback no puede existir. Decidido con el usuario: **503 ahora**; el
PR 2 añade el fallback junto con `fallback_used`. El plan se actualizó para reflejarlo.

### 2. `sources` también se mueve al PR 2

`AnswerDTO` del plan incluía `sources`. En el PR 1 siempre estaría vacío y su tipo depende de
`RetrievedDocument`, que nace en el PR 2. Meterlo ahora sería inventar contrato. Mismo
razonamiento que `fallback_used`. Reflejado en el plan.

### 3. `ServiceUnavailableError` en el shared kernel → 503

`LLMUnavailableError` hereda de un nuevo `ServiceUnavailableError(DomainError)` en
`shared/domain/errors.py`, y `exception_handlers.py` lo mapea a 503. Es el mismo mecanismo que ya
existía para 404/409/422 y evita que `shared` importe nada de `assistant` (dependencia invertida).

### 4. Modelo por defecto `claude-haiku-5-5`

El plan pedía «el modelo Claude más barato para dev». Configurable con `LLM_MODEL`.

### 5. SDK `anthropic>=2.3`

Versión publicada más reciente al empezar (2.3.0). Usa `httpx2`, no `httpx`.

### 6. Clasificación de errores del SDK (hallazgo #1 del code review)

Solo los fallos **transitorios** pasan a `LLMUnavailableError` → 503: `APIConnectionError`
(incluye `APITimeoutError`), `RateLimitError` (429) y `APIStatusError` con status ≥ 500 (incluye
529 overloaded). Los errores de **configuración** (400, 401, 403, 404: clave mala, modelo
inexistente, petición inválida) se propagan sin traducir → 500.

**Por qué:** un 503 invita a clientes y balanceadores a reintentar algo que nunca va a funcionar
y oculta la causa. Contradice el plan original («maps SDK errors to `LLMUnavailableError`»); el
plan se actualizó. El contrato está documentado en el docstring del puerto `LLMClient`.

### 7. Sin credenciales → 500, no 503

Con SDK 2.3.0, `AsyncAnthropic(api_key=None)` se construye sin error y lanza `TypeError` al
primer request si no encuentra credenciales. Es un error de configuración, coherente con la
decisión 6. (El code review afirmaba que fallaba en el constructor con `AnthropicError`; se
comprobó empíricamente que no.)

### 8. `LLM_MAX_RETRIES` (default 0); timeout y reintentos fijados una vez (hallazgos #3 y #5)

El SDK reintenta 2 veces por defecto, así que con `LLM_TIMEOUT_S=30` el peor caso eran ~90 s,
aunque la setting decía «timeout por petición». Ahora `LLM_TIMEOUT_S` es por intento,
`LLM_MAX_RETRIES` es explícito (default 0) y la cota es `timeout * (retries + 1)`.

El adaptador aplica `with_options(timeout, max_retries)` **una vez en el constructor**, no en cada
llamada (antes clonaba el cliente en cada request).

### 9. `FakeLLMClient` en `tests/fakes/llm_client.py` (hallazgo #9)

Antes los tests unitarios y e2e importaban el fake desde un `conftest.py` unitario. Ahora vive en
un módulo de helpers compartido; el `conftest` unitario solo expone la fixture.

### 10. Docstrings: solo en puertos y en lo que acaba en OpenAPI

Regla añadida al `CLAUDE.md` del repo. Se permiten docstrings en los **puertos** (para lo que los
tipos no expresan: qué excepciones y cuándo, invariantes, límites de tiempo) y en lo que acaba en
**OpenAPI**. Fuera de eso, nada.

En consecuencia se quitaron los docstrings nuevos de este PR y **todos** los de
`shared/domain/errors.py`, incluidos los preexistentes «Maps to HTTP 404/409/422»: ese mapeo ya
está en código (`exception_handlers.py`) y un docstring que lo repite puede quedarse desfasado.
En su lugar, `tests/e2e/test_exception_handlers.py` comprueba el código de estado de cada error.

### 11. Tests del adaptador en `tests/integration/`

El adaptador se prueba con el cliente real del SDK y `httpx2.MockTransport` (sin red, sin coste).
No es lógica pura (no va en `unit/`) y ejercita el adaptador real con su cliente HTTP, que es lo
que define la suite de integración.

## Code review: hallazgos no aplicados y porqué

| # | Hallazgo | Decisión |
|---|---|---|
| 4 | Respuesta vacía (refusal) o truncada (`max_tokens`) devuelve 200 | Requiere decidir contrato (status, flag). No está en el plan. Pendiente de decisión. |
| 6 | El `AsyncAnthropic` cacheado no se cierra en shutdown | El `engine` de SQLAlchemy tampoco se cierra; no hay lifespan en el repo. Introducirlo sería patrón nuevo; mejor como cambio transversal. |
| 7 | `max_length=1000` del schema se mide antes del strip y duplica la constante del dominio | El catálogo hace lo mismo (`ProductCreate.name`). Arreglarlo solo aquí rompe la consistencia. |
| 8 | 422 con dos formas (`detail` lista de Pydantic vs string del dominio) | Ya ocurre en el catálogo (currency inválida). Cambio transversal, fuera de alcance. |

## Fuera de alcance de este paso (pero hecho en la misma rama)

- **README**: cabecera centrada con badges (CI en vivo, tests, arquitectura, mypy strict, Python,
  FastAPI, Pydantic, PostgreSQL, Docker, Claude) y enlaces a secciones. El badge de tests es
  estático: hay que actualizarlo a mano. El README todavía dice «`catalog` is the only context so
  far»; su actualización está en el «Done means» del plan.
- **Repositorio GitHub**: descripción «Reference FastAPI project built with DDD and Hexagonal
  (Ports & Adapters) architecture.» y topics `fastapi`, `ddd`, `hexagonal-architecture`. `rag` y
  `langgraph` se añadirán cuando se fusionen los PR 2 y 3 (no antes: los topics reflejan lo que
  hay en `main`). La cuenta `gh` activa (`jcmorodiaz`) no tiene permisos de escritura; se usó el
  token de `jcmoro` solo para ese comando.

## Verificación

### Rojo (código sin modificar, antes del fix de #1 y #3)

```
FAILED TestErrorClassification::test_configuration_error_propagates[400-BadRequestError]
FAILED TestErrorClassification::test_configuration_error_propagates[401-AuthenticationError]
FAILED TestErrorClassification::test_configuration_error_propagates[403-PermissionDeniedError]
FAILED TestErrorClassification::test_configuration_error_propagates[404-NotFoundError]
FAILED TestTimeoutBound::test_timing_out_upstream_is_attempted_once   (assert 3 == 1)
```

Los 400–404 salían como `LLMUnavailableError`; el upstream que hace timeout se intentaba 3 veces.
Los 5 casos transitorios (429/500/529, conexión, timeout) ya pasaban y quedan como regresión.

### Verde (tras el fix)

```
tests/integration/contexts/assistant  → 10 passed
make lint  → ruff: All checks passed! · pylint: 10.00/10 · mypy: no issues found in 53 source files
make test  → 99 passed
```

Tests del contexto `assistant` + mapeo de errores: 31 (unit 12, e2e 9, integración 10).

### OpenAPI

`POST /assistant/ask` → tag `assistant`, summary «Ask the assistant», responses `200`, `422`,
`503`.

### Fronteras de arquitectura

```
grep imports en assistant/domain y assistant/application → solo stdlib, shared.domain y el propio contexto
grep "contexts.catalog" en src/contexts/assistant        → sin resultados
```

## Pendiente

- Decidir el contrato para respuestas vacías/truncadas (hallazgo #4).
- Disparador de indexación (síncrono vs evento) para el PR 2. Ojo: re-indexar síncronamente
  dentro de `CreateProduct` haría que `catalog` dependa de `assistant`.
- Tras el `make install` el `db-test` (tmpfs) se recrea vacío: hace falta `make migrate-test`
  antes de `make test` en local.
