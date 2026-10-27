# Paso 15 — README: presentar el proyecto como IA Generativa

Rama `feature/assistant-llm-port` (PR #4).

## Qué

Reescribir la cabecera y las secciones del `README.md` para que el proyecto se presente como una
**referencia de backend de IA Generativa** con arquitectura limpia (FastAPI + DDD + Hexagonal), sin
atribuirle nada que no exista en el código.

Concretamente:

1. Cabecera centrada con el posicionamiento GenAI y un enlace rápido a la sección «What works today».
2. Sección **Why this project**, con lo que el diseño ya garantiza hoy.
3. Sección **What works today**: el endpoint real `POST /assistant/ask`, un ejemplo de llamada y su
   contrato de errores.
4. Sección **Roadmap** con los 4 PR del plan (`docs/plan-assistant-genai.md`) y su estado.
5. Corregir lo que ha quedado desfasado: el badge de tests (decía 85), la frase «`catalog` is the
   only context so far», el layout sin el contexto `assistant` y la tabla de testing.

## Por qué

- Petición del usuario: «vender el proyecto como IA Generativa».
- Decidido con el usuario:
  - **Dónde**: en la PR #4. El README entra en `main` junto con el código que describe, así que
    `main` nunca promete algo que no tiene.
  - **Cómo tratar lo no construido**: un roadmap con estado explícito (✅ hecho / ⏳ planificado).
    Se puede vender con ambición sin presentar RAG, agente o despliegue como si existieran.
- Idioma del README: inglés, como el resto del fichero. Este documento va en español.

## Criterios de aceptación

| # | Criterio | Cómo se demuestra |
|---|---|---|
| 1 | Todo lo que el README presenta como **hecho** existe en el código de la rama | Tabla de trazabilidad: afirmación → fichero o test |
| 2 | Nada del roadmap aparece como hecho salvo el PR 1 | Revisión de la tabla Roadmap |
| 3 | Las cifras son reales | Badge de tests = recuento de `pytest --collect-only` en la rama |
| 4 | Las anclas internas de la cabecera apuntan a secciones existentes | Comprobación de anclas contra los encabezados |
| 5 | Los ejemplos de request y response coinciden con el contrato real | Contrastados con `ui/schemas.py` y los tests e2e |
| 6 | No se tocan código ni tests | `git diff --stat` solo muestra `README.md` y este documento |

## Evidencia

### C1 — Trazabilidad: afirmación del README → código

| Afirmación (README) | Dónde se comprueba |
|---|---|
| «The LLM is a port» / el dominio define `LLMClient` | `src/contexts/assistant/domain/ports/llm_client.py` |
| Domain y application no importan `anthropic` | `grep -rl anthropic src/contexts/assistant` → solo `infrastructure/llm/anthropic_llm_client.py` y `ui/dependencies.py` |
| `assistant` nunca importa `catalog` | `grep -rn contexts.catalog src/contexts/assistant` → sin resultados |
| Los tests nunca llaman a un modelo real | `tests/fakes/llm_client.py` (`FakeLLMClient`). El adaptador se prueba con `httpx2.MockTransport` en `tests/integration/.../test_anthropic_llm_client.py` |
| 503 para conexión, timeout, 429 y 5xx; los errores de configuración no se convierten en 503 | `anthropic_llm_client.py` (`except (APIConnectionError, RateLimitError)`, `status_code < 500 → raise`). Tests `test_transient_*` y `test_configuration_error_propagates` |
| `LLM_TIMEOUT_S` por intento, `LLM_MAX_RETRIES` = 0 por defecto, cota `timeout * (retries + 1)` | `src/shared/infrastructure/settings.py`. Test `test_timing_out_upstream_is_attempted_once` |
| La respuesta incluye modelo, tokens y latencia | `ui/schemas.py` (`UsageResponse`). Test e2e `test_returns_200_with_answer_and_usage` |
| 422: pregunta vacía, en blanco, de más de 1.000 caracteres o con campos extra | `AskRequest` (`min_length=1`, `max_length=1000`, `extra="forbid"`) + `Question`. Tests e2e 422 y `test_question.py` |
| Modelo por defecto `claude-haiku-5-5`; todas las variables LLM en `.env.example` | `settings.py`, `.env.example` |
| Cada error de dominio se comprueba contra su código de estado | `tests/e2e/test_exception_handlers.py` |

### C2 — Roadmap

Solo el paso 1 aparece como ✅, y se fusiona junto con este README en la PR #4. Los pasos 2, 3 y 4
aparecen como ⏳ Planned y su alcance copia el de `docs/plan-assistant-genai.md`. El README
también aclara que el assistant todavía no lee el catálogo.

### C3 — Cifras

`pytest --collect-only` sobre la rama (`9258f58`) recoge **99 tests**, 31 de ellos del assistant.
El badge dice `tests-99 passing`. Ambos badges nuevos o cambiados devuelven HTTP 200 en shields.io.

### C4 — Anclas

Las 6 anclas de la cabecera (`#what-works-today`, `#why-this-project`, `#roadmap`,
`#quick-start`, `#architecture`, `#testing`) tienen su encabezado `##` correspondiente.

### C5 — Ejemplos

- El request `{"question": ...}` coincide con `AskRequest`.
- La response `{"text", "usage": {"model", "input_tokens", "output_tokens", "latency_ms"}}`
  coincide con `AnswerResponse` y `UsageResponse`.
- Los valores del ejemplo están marcados como ilustrativos.

### C6 — Alcance

`git status` solo muestra `README.md` modificado y este documento. No se toca código ni tests.
