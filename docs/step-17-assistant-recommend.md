# Paso 17 — Contexto `assistant`: read model y selección de candidatos (PR 3a)

Rama `feature/assistant-recommend`. Plan: `docs/plan-assistant-genai.md`, sección «PR 3a — Read
model y selección de candidatos». El agente LangGraph va en el PR 3b (`docs/step-18-assistant-agent.md`).

## Objetivo

Que, dada una pregunta como «¿cuál de estos me recomiendas para X?» y los candidatos recuperados,
`RecommendCandidate` devuelva una de dos cosas:

- **un producto recomendado**, elegido por reglas en código;
- **ninguno**, con su razón (`below_threshold` o `no_assessments`).

La elección es siempre determinista y la decisión nunca la toma el modelo. Además, el índice gana
las columnas `sku`, `name` y precio que necesitará el PR 3b.

## Qué

1. **Read model:** una migración añade a `product_documents` las columnas `sku` (índice único),
   `name`, `price_cents` y `currency`. Las rellena `IndexCatalog` desde el DTO del catálogo. Las
   filas con alguna de esas columnas a nulo cuentan como cambiadas, así que el siguiente reindexado
   las rellena.
2. **Orden en `IndexCatalog`:** los huérfanos confirmados se borran **antes** del upsert.
3. **Dominio:**
   - `Candidate`, `Assessment` y `Selection`;
   - el puerto `CandidateAssessor`;
   - la rúbrica, definida una vez en código;
   - la función pura `select`.
4. **Aplicación:** el caso de uso `RecommendCandidate`:
   - pasa al evaluador solo el top `selector_top_n`;
   - evalúa en paralelo, como mucho 10 a la vez, con un plazo global de 10 s;
   - aplica `select`, con fallback determinista si no se pudo evaluar ningún candidato;
   - escribe una línea de log por selección.
5. **Infraestructura:** `ClaudeCandidateAssessor`, directo sobre el SDK de Anthropic con salida
   estructurada y self-consistency (3 muestras). Reutiliza la clasificación de errores del PR 1.
6. **Settings:** `selector_provider` (solo `claude`), `selector_top_n`, `selector_max_concurrency`,
   `selector_timeout_s`, `selector_samples`, `selector_requirements_threshold` y
   `selector_min_score`.
7. **Fake** `FakeCandidateAssessor` para los tests.

## Por qué

- El PR 2 responde con contexto, pero no decide. Preguntas como «¿cuál me recomiendas para X?»
  necesitan elegir uno, o reconocer que no se puede, sin que la elección dependa de cómo se
  presentan los candidatos.
- **El modelo lee y el código decide.** Es una decisión de diseño de este proyecto: elegir entre
  varios productos en una sola pregunta puede depender del orden de presentación. Evaluar cada uno
  por separado y ordenar en código lo evita, y la eval de invariancia al orden (PR 3b) lo
  comprueba.
- Separar 3a de 3b deja la parte determinista y comprobable sin red (selección, índice) en un PR
  propio, antes de introducir LangGraph.

## Fuera de alcance

- **PR 3b:** el agente LangGraph, sus herramientas (incluida `recommend_candidate` y cómo presenta
  el caso sin recomendación), el límite de pasos, `assistant_mode` y las evals.
- **PR 5:** el evaluador jev.
- **PR 4:** el despliegue.
- **Punto de entrada:** en 3a, `RecommendCandidate` solo lo ejercitan sus tests. No cambia ningún
  comportamiento existente.
- **Cambios en `catalog`**: ni una línea.
- **Llamadas reales a Anthropic**: todo se demuestra con fakes y `httpx2.MockTransport`.

## Decisiones tomadas (con el usuario)

| Tema | Decisión | Porqué |
|---|---|---|
| Rúbrica | Dos `noul`. `meets_requirements` es un **filtro**: si la pregunta no tiene requisitos explícitos, se responde sí. `suitable_for_use` **ordena**, sin pesos. | Un requisito explícito no se compensa con idoneidad; la idoneidad es lo único que ordena. |
| Puntuación | La probabilidad de `suitable_for_use` | Una sola magnitud, fácil de interpretar y de calibrar. |
| `score` y números | `score` nunca entra en una ordenación, y los números nunca se le preguntan al modelo | La expectativa de `score` no está calibrada entre niveles, y los modelos de decisión no comparan magnitudes con fiabilidad. |
| Probabilidad con Claude | Self-consistency con `selector_samples` = **3**. Las dos preguntas van en la misma llamada. | Claude no devuelve probabilidades. La confianza que declara el propio modelo está mal calibrada. |
| Umbrales | `selector_requirements_threshold` = 0,5 y `selector_min_score` = 0,5, ambos con `>=`. Las evals (PR 3b) fijan los valores finales. | Con 3 muestras los valores posibles son 0; 0,33; 0,67 y 1, así que 0,5 equivale a «mayoría sí». |
| Desempate | Gana el mejor `retrieval_score`; si también empatan, el `product_id` menor | Elección siempre determinista. El segundo criterio lo añadí yo para cubrir el doble empate. |
| Candidatos | Solo el top `selector_top_n` = 10 llega al evaluador, independiente de `rag_top_k` | Son dos necesidades distintas: entre cuántos se elige y cuánto contexto recibe el LLM. |
| Concurrencia y plazo | Como mucho 10 evaluaciones a la vez, con un plazo global de 10 s | 10 × 3 = 30 llamadas, unas 3 rondas (~3 s). |
| 429 | Error transitorio (clasificación del PR 1): ese candidato queda sin evaluar. El log registra las llamadas hechas y las contestadas. | Una ráfaga de 30 llamadas puede chocar con límites bajos de la cuenta, y las evals deben detectarlo. |
| Columnas del read model | `sku` (índice único), `name`, `price_cents` y `currency`, rellenadas desde el DTO. Las filas con nulos se tratan como cambiadas. | Antes estaban solo dentro de `content`. Así `catalog` no cambia. |
| `Candidate` | Lleva `content` (el texto del documento) en lugar de `description` | El catálogo no tiene descripción de producto. |
| Orden en `IndexCatalog` | Huérfanos confirmados borrados **antes** del upsert | Con el índice único, un SKU reutilizado entre dos reindexados haría chocar el upsert y el reindexado entero haría rollback. |
| `ClaudeCandidateAssessor` | Directo sobre el SDK de Anthropic, con salida estructurada y la clasificación de errores del PR 1 | Es un adaptador. El puerto `LLMClient` solo devuelve texto y no cambia. |
| PR 3 dividido | 3a (este) y 3b (agente) | Petición del usuario. |

## Criterios de aceptación

| # | Criterio | Cómo se demuestra |
|---|---|---|
| A1 | `select` filtra por `meets_requirements >= umbral`, ordena por `suitable_for_use`, desempata por `retrieval_score` y después por `product_id`, y aplica `>= min_score` | Tests unitarios de la función pura, incluido el caso exacto en el umbral |
| A2 | Nunca se devuelve un producto que no esté entre los candidatos, y barajar la entrada no cambia la selección | Tests unitarios |
| A3 | Self-consistency: 3/3 → 1,0; 2/3 → 0,67; 1/3 → 0,33. Una muestra inválida, o cortada por `max_tokens`, deja el candidato sin evaluar (CR2) | Tests del adaptador con el cliente de Anthropic sobre `httpx2.MockTransport` y respuestas guionizadas |
| A4 | `ClaudeCandidateAssessor` clasifica los errores como el PR 1: los transitorios dan `LLMUnavailableError` y los de configuración se propagan | Tests del adaptador |
| A5 | `RecommendCandidate` solo evalúa el top `selector_top_n`. Nunca hay más de `selector_max_concurrency` **llamadas** en vuelo (CR1). Lo que no llega en plazo cuenta como no evaluado. | Tests con un evaluador falso que simula retrasos; test del evaluador que mide las llamadas en vuelo |
| A6 | Si falla un candidato, se elige entre el resto. Si fallan todos, fallback ordenado por `retrieval_score` con `fallback_used=true` y razón `no_assessments` | Tests unitarios |
| A7 | `product_documents` tiene `sku` único, `name`, `price_cents` y `currency`. El reindexado los rellena desde el DTO, y las filas con nulos se recalculan | Test unitario del relleno, test de integración de la migración y `make reindex` real |
| A8 | Borrar un producto y crear otro con el mismo SKU entre dos reindexados no rompe el reindexado | Test que **falla con el orden actual** y pasa con el nuevo |
| A9 | Una línea de log por selección con proveedor, modelo, llamadas hechas y contestadas, latencia, tokens, coste y razón, sin datos de producto más allá de los ids | Test con `caplog` |
| A10 | El dominio y la aplicación de `assistant` no importan `anthropic` | `grep` |
| A11 | Los quality gates y el CI pasan | `make lint`, `make test` y CI de la PR |
| A12 | El plan y el README coinciden con el código | Revisión y badge de tests |

## Decisiones tomadas durante la implementación

| Tema | Decisión | Porqué |
|---|---|---|
| Firma de `select` | `select(candidates, assessments, requirements_threshold, min_score)`, no `select(assessments, …)` | El desempate necesita el `retrieval_score` de cada candidato, y solo se puede devolver uno de ellos. El plan está corregido. |
| Incompletos en el índice | `DocumentIndex.content_hashes()` devuelve `None` para las filas sin columnas de catálogo | `IndexCatalog` las trata como cambiadas sin lógica nueva, porque `None != hash`. |
| Muestras de Claude | ~~Secuenciales, con la concurrencia por candidato~~ → **en paralelo, con un semáforo por llamada** (CR1) | Con muestras seguidas, todos los candidatos acababan en la 3.ª ronda y un plazo corto los dejaba a todos sin evaluar. |
| Muestras inválidas | ~~No cuentan como sí~~ → **cualquier muestra inválida, fallida o que no llega deja el candidato sin evaluar** (CR2) | Regla del usuario. Las puntuaciones quedan en k/3 y los fallos del modelo se separan de sus juicios. |
| `effort` y `max_tokens` del evaluador | `output_config.effort = "low"` y ~~`max_tokens = llm_max_tokens` (4096)~~ → `selector_max_tokens` = 1024 (CR6) | El modelo por defecto (`claude-haiku-5-5`) piensa por defecto y esos tokens cuentan contra `max_tokens`. Con un límite pequeño, una muestra podría acabarse sin JSON. `low` mantiene corto el razonamiento de una clasificación sí/no. No se desactiva el thinking porque en otros modelos (`claude-opus-5-5`) `disabled` devuelve 400. |
| Clasificación de errores | Extraída a `anthropic_errors.transient_errors_as_unavailable()` y compartida por `AnthropicLLMClient` y `ClaudeCandidateAssessor` | Una sola regla; los tests del PR 1 siguen en verde sin cambios. |
| Uso por evaluación | `Assessment.usage` (`api_calls`, `input_tokens`, `output_tokens`, `cost_usd`) | El log de la selección suma el uso real de las evaluaciones completadas. |
| «Llamadas hechas y contestadas» en el log | `candidates` (evaluaciones pedidas), `assessed` (con respuesta útil), `api_calls` y tokens (también los de las evaluaciones que fallan a medias, CR4), y `unassessed=<id>:<razón>` | Un 429 o un timeout dejan `assessed < candidates` con su razón, que es lo que las evals tienen que detectar. |
| Coste con Claude | `cost_usd=None` | La Messages API no devuelve el coste. Calcularlo exigiría una tabla de precios en settings, que no está pedida. jev (PR 5) sí lo devuelve. |
| Errores de configuración en paralelo | `asyncio.wait(..., return_when=FIRST_EXCEPTION)`, cancelación de todo lo pendiente en un `finally`, y relanzar la primera excepción tras recuperarlas todas (CR3) | Se propaga en el acto, no deja llamadas huérfanas al cancelar la petición, y asyncio no avisa de excepciones sin recoger. |
| `selector_provider` | `Literal["claude"]` | Solo existe ese evaluador; el PR 5 añade `jev`. |
| Proveedores de dependencias | Ninguno en 3a (CR5). En 3b, reutilizando el único cliente de Anthropic del asistente, el que se cierra en el lifespan. | En 3a no hay punto de entrada, y eran código muerto con un segundo cliente HTTP. |
| Uso al fallar | `AssessmentUnavailableError(LLMUnavailableError)` lleva `usage`. `AssessmentUsage` vive en su propio módulo. | El puerto no cambia de contrato (CR4), y el módulo propio evita una importación circular entre `candidate` y `exceptions`. |

## Correcciones tras la code review

La revisión (`/code-review medium`) dio 10 hallazgos y se comprobó cada uno contra el código. 4 son
reales y cambian el comportamiento, 2 son mejoras y se aplican, y 3 son falsos positivos (detalle al
final de esta sección). El hallazgo #2 se resolvió con una regla nueva del usuario. Cada corrección
empieza por un test que falla con el código anterior.

| # | Qué | Por qué | Criterio de aceptación |
|---|---|---|---|
| CR1 | **El límite de concurrencia se aplica por llamada, no por candidato.** `selector_max_concurrency` (10) es el número de llamadas a la API en vuelo. Las 3 muestras de un candidato salen juntas, así que los candidatos van terminando uno tras otro. | Antes, los 10 candidatos arrancaban a la vez y cada uno hacía 3 muestras seguidas: todos acababan en la 3.ª ronda. Con llamadas lentas (~4 s), a los 10 s no terminaba **ninguno** y la respuesta caía siempre al fallback (todo o nada). | Nunca hay más de `selector_max_concurrency` llamadas en vuelo. Con llamadas lentas y el plazo a mitad, **algunos** candidatos llegan evaluados en lugar de ninguno. |
| CR2 | **Un candidato solo participa con las 3 muestras válidas.** Cualquier muestra inválida, fallida o que no llegue lo deja sin evaluar, y su razón (`invalid_sample`, `error` o `deadline`) queda en el log. Una respuesta cortada por `max_tokens` es una muestra inválida. | Decisión del usuario. Las puntuaciones se quedan en 0 / 0,33 / 0,67 / 1, y en las evals los fallos del modelo se separan de sus juicios. | Una muestra inválida deja el candidato sin evaluar con `invalid_sample`. Un corte por `max_tokens` es inválido. Si todos quedan sin evaluar, fallback determinista. El log trae la razón de cada candidato sin evaluar. |
| CR3 | **Cancelar y cortar antes de tiempo.** Si se cancela la petición, se cancelan todas las evaluaciones en curso. Ante un error de configuración se propaga en el acto, sin esperar al plazo. | Antes las llamadas seguían ejecutándose y facturándose en segundo plano, y un 401 esperaba los 10 s. | Al cancelar `execute`, se cancelan todas las evaluaciones. Un error de configuración se propaga en mucho menos que el plazo. |
| CR4 | **No perder el uso.** El puerto sigue lanzando `LLMUnavailableError` ante fallos transitorios, pero la excepción lleva el uso acumulado (`AssessmentUnavailableError`, subclase). El caso de uso lo suma al de la selección. | Antes, si fallaba la 3.ª muestra, se perdían los tokens de las dos primeras y el log se quedaba corto. | Si falla una muestra, el log incluye los tokens de las demás. |
| CR5 | **Quitar los proveedores sin uso** `get_candidate_assessor` y `get_recommend_candidate_use_case`. En el 3b se añaden, reutilizando el único cliente de Anthropic del asistente, el que se cierra en el lifespan. | Eran código muerto en 3a y creaban un segundo cliente HTTP. | `grep`: no existen en 3a. |
| CR6 | **`selector_max_tokens` propio, 1024 por defecto.** El razonamiento no se desactiva: se mantiene `effort: "low"`. | Dos booleanos no necesitan 4096. No se desactiva el razonamiento porque `thinking: disabled` devuelve 400 en `claude-opus-5-5` y en `claude-sonnet-5-5`, y el evaluador usa `llm_model`, que es configurable. | La petición lleva `max_tokens = selector_max_tokens`. Un corte por `max_tokens` es inválido (CR2). |

**Falsos positivos:**

- **«Intercambiar SKUs rompe el índice único».** En `catalog` el SKU no se puede modificar
  (`UpdateProductCommand` no tiene `sku`). El único caso real, borrar y crear con el mismo SKU, ya lo
  cubre A8.
- **«Borrar huérfanos antes del upsert deja huecos si algo falla».** El reindexado va en una sola
  transacción (`get_session`) y ante cualquier error hace rollback completo.
- **«Docstrings narrativos en los puertos».** El `CLAUDE.md` del repo los permite en los puertos,
  para lo que los tipos no expresan.

## Evidencia

### Rojo antes del verde

```
Paso 1 (read model):
FAILED test_product_document.py::TestCatalogFields::test_a7_carries_the_catalog_fields
FAILED test_index_catalog.py::TestReadModelColumns::test_a7_reindexes_documents_missing_catalog_columns
FAILED test_index_catalog.py::TestReadModelColumns::test_a8_a_reused_sku_does_not_break_the_reindex
FAILED test_sqlalchemy_documents.py::TestReadModelColumns::test_a7_upsert_stores_the_catalog_columns
FAILED test_sqlalchemy_documents.py::TestReadModelColumns::test_a7_a_row_missing_catalog_columns_reports_no_hash
FAILED test_sqlalchemy_documents.py::TestReadModelColumns::test_a8_sku_is_unique_in_the_index
A8 con las columnas ya añadidas, rojo por el bug de orden:
  tests.fakes.documents.DuplicateSkuInIndexError: SKU-REUSED
Paso 2 (select):        ModuleNotFoundError: contexts.assistant.domain.candidate
Paso 3 (evaluador):     ModuleNotFoundError: ...infrastructure.llm.claude_candidate_assessor
Paso 4 (caso de uso):   ModuleNotFoundError: ...application.use_cases.recommend_candidate
```

El A8 se separó a propósito: primero se añadieron las columnas, se comprobó que el test seguía
fallando por el **orden** (upsert antes de borrar el huérfano con el mismo SKU) y solo entonces se
cambió el orden.

Correcciones de la code review, sobre el código anterior:

```
CR1 (comportamiento, API anterior):
  test_cr1_slow_calls_still_assess_some_candidates_before_the_deadline → assert 0 >= 1
  (con llamadas de 0,2 s y plazo de 0,5 s, ningún candidato llegaba evaluado)
Con el dominio nuevo añadido, rojo por comportamiento:
  CR3 test_cr3_a_configuration_error_does_not_wait_for_the_deadline → esperó 3,0 s (> 1,0)
  CR3 test_cr3_cancelling_the_request_cancels_every_assessment      → assert 0 == 3
  CR4 test_cr4_usage_of_a_failed_assessment_is_logged               → api_calls=3 (se perdía el uso)
  CR2 test_cr2_unassessed_candidates_are_logged_with_their_reason   → sin razones en el log
Evaluador (API nueva: max_concurrency):
  CR2 one_invalid_sample / cut_by_max_tokens, CR4 carries_the_usage, CR1 never_more_calls → FAILED
CR6 test_cr6_the_assessor_has_its_own_output_limit → FAILED (no existía el setting)
```

Verde de las correcciones: `10 passed` (CR1×2, CR2×3, CR3×2, CR4×2, CR6). CR5 con `grep`: ni
`get_candidate_assessor` ni `get_recommend_candidate_use_case` existen en 3a.

### Verde

| # | Resultado | Evidencia |
|---|---|---|
| A1 | ✅ | `test_selection.py` (18 tests): ordenación, desempate por `retrieval_score` y por `product_id`, filtro de requisitos, umbrales exactos con `>=` y todos por debajo |
| A2 | ✅ | `test_a2_never_returns_a_product_outside_the_candidates`; `test_a2_shuffled_input_gives_the_same_selection` (todas las permutaciones de 4); el mismo resultado con entrada barajada en `RecommendCandidate` |
| A3 | ✅ | `test_claude_candidate_assessor.py`: 3/3 → 1,0; 2/3 → 0,67; 1/3 → 0,33; una muestra inválida, o cortada por `max_tokens`, deja el candidato sin evaluar con `invalid_sample` (CR2); esquema estricto; sin `temperature`; `effort=low` |
| A4 | ✅ | 429, 500, 529 y la conexión dan `LLMUnavailableError`; 400 y 401 se propagan |
| A5 | ✅ | `test_recommend_candidate.py`: solo el top N por `retrieval_score`; el candidato fuera de plazo cuenta como no evaluado (`deadline`). `test_cr1_never_more_calls_in_flight_than_the_limit`: pico de llamadas = límite. `test_cr1_slow_calls_still_assess_some_candidates_before_the_deadline`: con llamadas lentas, llegan candidatos evaluados |
| A6 | ✅ | Un fallo transitorio salta solo ese candidato; si fallan todos → fallback ordenado por `retrieval_score` con `no_assessments`; un error de configuración se propaga |
| A7 | ✅ | Tests unitarios y de integración del relleno. **`make reindex` real** tras la migración, sobre la BD de desarrollo: `indexed=3 unchanged=0 deleted=0` (relleno) y después `indexed=0 unchanged=3 deleted=0`; las filas tienen `sku`, `name`, `price_cents` y `currency` |
| A8 | ✅ | `test_a8_a_reused_sku_does_not_break_the_reindex` (rojo por el orden → verde); `test_a8_sku_is_unique_in_the_index` contra Postgres real (`IntegrityError`) |
| A9 | ✅ | `test_a9_one_line_per_selection_with_ids_only`: una sola línea con `provider`, `model`, `candidates`, `assessed`, `api_calls`, tokens, `cost_usd`, `latency_ms`, `reason` y `product_id`; no aparecen SKU, nombre ni texto de la pregunta |
| A10 | ✅ | `grep` sin resultados: el dominio y la aplicación de `assistant` no importan `anthropic`, `sqlalchemy`, `fastapi`, `pgvector`, `fastembed` ni `httpx`. `catalog` sin cambios. Los e2e del PR 2 sin cambios. Ningún `type: ignore`, `noqa` ni `pylint: disable` nuevo. |
| A11 | ✅ | `make lint`: ruff OK, pylint 10.00/10, mypy sin errores (80 ficheros). `make test`: **192 passed** (antes 137), sin avisos de excepciones sin recoger. **CI de la PR #9:** run `40599241763` sobre `6bbbd65`, en verde (login, build, migraciones, lint y tests en ambos jobs). |
| A12 | ✅ | Plan con la firma real de `select` y las correcciones CR1–CR6; README con el badge de 192 tests y el layout de los ficheros nuevos |

### Tests nuevos o ampliados

| Fichero | Tests |
|---|---|
| `tests/unit/contexts/assistant/domain/test_selection.py` | 18 (nuevo) |
| `tests/unit/contexts/assistant/application/test_recommend_candidate.py` | 12 (nuevo) |
| `tests/integration/contexts/assistant/infrastructure/test_claude_candidate_assessor.py` | 17 (nuevo) |
| `tests/integration/contexts/assistant/application/test_recommend_candidate_deadline.py` | 1 (nuevo, CR1) |
| `tests/unit/shared/infrastructure/test_settings.py` | 3 (+1, CR6) |
| `tests/unit/contexts/assistant/application/test_index_catalog.py` | 11 (+2) |
| `tests/unit/contexts/assistant/domain/test_product_document.py` | 7 (+1) |
| `tests/integration/contexts/assistant/infrastructure/test_sqlalchemy_documents.py` | 10 (+3) |

### Fuera de lo verificado

- **Llamadas reales a Anthropic:** en 3a no se hace ninguna. El evaluador se prueba con
  `httpx2.MockTransport`. Las llamadas reales llegan con las evals del PR 3b, y antes de la primera se
  informa del número de llamadas y del modelo.
