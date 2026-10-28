# Paso 18 — Contexto `assistant`: agente con LangGraph (PR 3b)

Plan: `docs/plan-assistant-genai.md`, sección «PR 3b — Agente con LangGraph». Se apoya en el PR 3a
(`docs/step-17-assistant-recommend.md`). Este documento se completa al empezar el PR 3b; de momento
recoge el alcance y los criterios ya decididos, para que no se pierdan con la división del PR 3.

## Objetivo

Que, con `assistant_mode=agent`, una pregunta como «¿cuál de estos me recomiendas para X?» acabe
de una de dos formas:

- con **un producto recomendado**, a través de `recommend_candidate`;
- con un **«no hay una recomendación clara»** explícito y el top-k (nombre, SKU y precio).

En ambos casos el agente queda acotado en pasos, tiempo y coste. Con `assistant_mode=rag`, el valor
por defecto, todo sigue igual que en el PR 2.

## Qué

1. Agente LangGraph detrás del puerto `CatalogAgent`, con las herramientas `semantic_search`,
   `get_product_by_sku` y `recommend_candidate`.
2. Como mucho 5 llamadas a herramientas por ejecución (`recommend_candidate` cuenta como una). Al
   llegar al límite, el agente responde en modo RAG con lo recuperado y registra la razón
   `max_steps`.
3. LangGraph solo orquesta. El nodo del modelo llama al SDK de Anthropic directamente (tool use) a
   través de nuestro adaptador, con el único cliente del asistente y la clasificación de errores del
   PR 1. Cada herramienta se define una vez (esquema + handler).
3b. `AnswerResponse` gana `recommendation: {product_id, sku, score, reason} | null`, que sale de la
   `Selection`, nunca del texto del modelo.
4. `assistant_mode` (`rag` | `agent`), con `rag` por defecto.
5. Evals con el marker `eval`, fuera del CI.

## Decisiones tomadas (con el usuario)

| Tema | Decisión |
|---|---|
| Límite de pasos | 5 llamadas a herramientas. Al llegar, respuesta en modo RAG y razón `max_steps` en el log. |
| `assistant_mode` | `rag` por defecto; el comportamiento en `rag` no cambia. En el JSON, `recommendation` está siempre presente y vale `null` en `rag`: omitir la clave crearía un tercer estado. Por eso un e2e del PR 2 gana esa clave en el diccionario esperado. |
| Sin recomendación | «No hay una recomendación clara» y el top-k con nombre, SKU y precio, sin pregunta de seguimiento. |
| LLM del agente | **Sin `langchain-anthropic`**: su última versión (1.7.6) exige `anthropic<2.0.0`. El nodo del modelo usa el SDK de Anthropic a través de nuestro adaptador, con el único cliente y la clasificación del PR 1. |
| Herramientas | Cada una se define **una vez** (esquema + handler); de ahí salen las definiciones que se envían a la API y el nodo de herramientas. |
| Límite de pasos (mecanismo) | Contador en el estado del grafo y arista condicional hacia el modo RAG; `recursion_limit` solo como red de seguridad. |
| Dependencias | Solo `langgraph` (>= 1.2.18). Resolver en seco con todas las dependencias del proyecto: `anthropic` 2.3.0, `langchain-core` 1.7.0 y `langchain-protocol`, sin `langchain-anthropic` y sin conflictos. |
| Contrato | `recommendation: {product_id, sku, score, reason} \| null` en `AnswerResponse`: opcional y aditivo. **`null` si el selector no se ejecutó** (modo `rag`, o el agente respondió sin recomendar). **Objeto si se ejecutó**: `reason` ∈ `chosen` \| `below_threshold` \| `no_assessments`, y `product_id`, `sku` y `score` son no nulos **si y solo si** `reason == "chosen"`, con un validador de Pydantic. Sale de la `Selection`, nunca del texto. |
| Razón de parada del agente | `answered` \| `max_steps`. Es un resultado del agente, no de la selección: va en el DTO del caso de uso y en el log, **no en la API** por ahora. |
| Dataset de evals | Material de montaña (cualquier dominio salvo viajes), ~20 productos y ~10 preguntas que describen el uso. Incluye productos casi idénticos que difieren en un requisito explícito, casos de no recomendar y al menos una pregunta ambigua. Conjuntos de SKUs aceptables. En `tests/evals/`, cargado de forma determinista en su propia BD. Resultados en recuentos. El usuario lo revisa antes de cualquier ejecución real. |
| Clave para las evals | El usuario pone `ANTHROPIC_API_KEY` en `.env`. **Su valor nunca aparece en logs, salidas de comandos ni documentos.** |
| Primera ejecución real de evals | **Antes de lanzarla se informa al usuario del número de llamadas y del modelo** que usará. |
| Cliente de Anthropic | Los proveedores de `RecommendCandidate` y de `ClaudeCandidateAssessor` se crean aquí y reutilizan el único cliente de Anthropic del asistente, que se cierra en el lifespan (decidido en la code review del 3a). |

## Criterios de aceptación

| # | Criterio | Cómo se demuestra |
|---|---|---|
| B1 | Sin recomendación, la respuesta dice que no hay una clara y lista el top-k con nombre, SKU y precio | Test del agente |
| B2 | Al llegar a la 5.ª llamada a herramienta se corta, responde en modo RAG y el log registra `max_steps` | Test del grafo con un modelo falso guionizado |
| B3 | `assistant_mode=rag` es el valor por defecto y el comportamiento en `rag` no cambia. Los e2e del PR 2 solo ganan la clave `"recommendation": None` en el diccionario esperado de `test_c7_returns_200_with_answer_sources_and_usage`, porque el contrato ganó un campo aditivo | `git diff` de esos tests limitado a esa línea, y suite en verde |
| B4 | Los errores del LLM del agente se clasifican como en el PR 1: los transitorios llevan al fallback y los de configuración se propagan | Test del adaptador del agente con errores simulados sobre `httpx2.MockTransport` |
| B5 | El dominio y la aplicación de `assistant` no importan `langgraph` ni `langchain`, y `langchain-anthropic` no está entre las dependencias | `grep` y `pip show` |
| B10 | `recommendation` es `null` si el selector no se ejecutó, y un objeto sacado de la `Selection` si se ejecutó. El texto del modelo nunca altera el campo. | Un e2e por modo (`rag`: `null`; `agent`: objeto) y un test con un modelo que «dice» otro SKU en el texto |
| B14 | Invariante: `product_id`, `sku` y `score` no nulos **si y solo si** `reason == "chosen"` | Test del validador de Pydantic: los cuatro casos inválidos dan error |
| B15 | La razón de parada del agente (`answered` \| `max_steps`) está en el DTO del caso de uso y en el log, y **no** en la respuesta HTTP | Test del DTO, test con `caplog` y un e2e que comprueba que el campo no está en el JSON |
| B11 | Cada herramienta se define una vez, y las definiciones de la API y el nodo de herramientas salen de ahí | Test que compara ambas con la definición única |
| B12 | El límite de pasos lo aplica el contador del estado y la arista condicional, no `recursion_limit` | Test del grafo |
| B13 | El dataset cumple sus reglas (dominio, uso en lugar de descripción, casi idénticos, no recomendar, ambigua, conjuntos aceptables) y se carga de forma determinista en su propia BD | Revisión del usuario y test de carga |
| B6 | Las evals existen con el marker `eval` y el CI por defecto no las ejecuta | Recolección de pytest y CI de la PR |
| B7 | Antes de la primera ejecución real se informa del número de llamadas, y el valor de la clave no aparece en ninguna salida | Mensaje al usuario antes de ejecutar, y revisión de las salidas |
| B8 | Los quality gates y el CI pasan | `make lint`, `make test` y CI de la PR |
| B9 | El plan y el README coinciden con el código | Revisión, anclas y badges |

## Plan de evals

**Dataset** — `tests/evals/dataset.json`, versión 2, aprobado por el usuario con dos cambios:

- 20 productos de material de montaña con **SKUs opacos** (`MT-0001`…`MT-0020`), para que el
  modelo no pueda leer la talla ni el color en el código.
- 10 preguntas: 7 `recommend`, 2 `no_recommendation` y 1 `ambiguous`, cada una con su conjunto de
  SKUs aceptables.
- Se carga de forma determinista en su propia base de datos (`catalog_eval`, en el servidor de
  `db-test`), nunca en los datos del usuario.

**Modelos** — las evaluaciones y el agente usan `claude-haiku-5-5` (`LLM_MODEL` por defecto; `.env`
no lo cambia). Los embeddings usan `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`:
comprobado que es **multilingüe** (~50 idiomas), y ni `.env` ni la imagen lo cambian, así que el
dataset en español no necesita otro modelo.

**Regla de puntuación** (decidida por el usuario):

| Tipo de pregunta | Cuenta como acierto | Cuenta como fallo |
|---|---|---|
| `recommend` | `reason = chosen` y SKU en el conjunto aceptable | otro SKU, `below_threshold`, `null` o `no_assessments` |
| con `accept_no_recommendation = true` (`no_recommendation`, `ambiguous`) | `reason = below_threshold`, `recommendation = null` (solo en E4), o, en la ambigua, `chosen` con un SKU aceptable | `chosen` con un SKU no aceptable, o `no_assessments` |

Cada resultado registra **qué ocurrió** (`chosen:<SKU>`, `below_threshold`, `null` o
`no_assessments`). `no_assessments` siempre cuenta como fallo: es un fallo del modelo, no un juicio,
y se informa aparte. Los resultados se dan en **recuentos** (por ejemplo «7/10: recommend 5/7,
no_recommendation 2/2, ambiguous 0/1»), nunca en porcentajes.

| Eval | Qué mide y cómo | Llamadas reales |
|---|---|---|
| **E1 · Selector** | `RecommendCandidate` con `ClaudeCandidateAssessor` real sobre cada pregunta: top 10 de la recuperación × 3 muestras. Precisión según la regla. Con las mismas evaluaciones se recalcula `select` (función pura, **sin llamadas nuevas**) para la tabla de umbrales: `requirements_threshold` y `min_score` ∈ {0,33; 0,67; 1,0}, con precisión y cobertura (cuántas veces recomienda) en recuentos. Con 3 muestras, 0,5 equivale a 0,67. | 300 |
| **E2 · Invariancia al orden** | E1 otra vez con los candidatos barajados; cuántas preguntas repiten el mismo resultado que en E1 | 300 |
| **E3 · Repetición** | E1 otra vez en el mismo orden; cuántas preguntas repiten el resultado de E1 | 300 |
| **E4 · Agente completo** | `AskAssistant` en modo `agent`, extremo a extremo, comparando `recommendation` con el conjunto aceptable. También registra la razón de parada, las llamadas a herramientas y la latencia. | ~330 |

Además, en cada eval: latencia por selección o por pregunta, tokens, y llamadas contestadas frente a
llamadas hechas. El coste de Claude se **estima** con los tokens y el precio de lista, porque la API
no lo devuelve.

**Hallazgo sobre E2 y E3, para decidir sobre E3.** Con este diseño, **barajar los candidatos no
cambia lo que ve el modelo**:

- Cada llamada evalúa un solo candidato.
- `RecommendCandidate` reordena la entrada por `retrieval_score` antes de evaluar.

Así que E2 manda exactamente las mismas 300 peticiones que una repetición, y E2 y E3 miden lo
mismo: la variabilidad del modelo entre ejecuciones. La invariancia al orden **del código** ya la
demuestran los tests unitarios sin coste (A2 y la entrada barajada en `RecommendCandidate`). La
invariancia al orden **del modelo** está garantizada por construcción, porque nunca ve dos
candidatos a la vez.

**Propuesta:** quedarse con una sola reejecución. Llamarla «E2 · Estabilidad (orden barajado)»
cubre ambas preguntas con 300 llamadas y deja el total en unas **930**.

**Decisión del usuario:** se ejecutan E2 y E3. Total previsto: ~1.230 llamadas.

### Harness

- **Ficheros:** `tests/evals/` (`harness.py`, `conftest.py`, `test_eval_selector.py` con E1–E3,
  `test_eval_agent.py` con E4). Llevan el marcador `eval`, que `pytest` excluye por defecto, y se
  lanzan con `make eval`.
- **Clave:** `make eval` monta `.env` en solo lectura. La clave se lee del fichero y no aparece en
  ningún comando.
- **Base de datos:** se crea `catalog_eval` en el servidor de `db-test` y se migra con `alembic`.
  Después se cargan los 20 productos con IDs `uuid5` fijos y se indexan con los embeddings locales.
- **Informe:**
  - una línea por eval que dice qué mide;
  - aciertos en recuentos por tipo de pregunta;
  - tokens y coste estimado;
  - llamadas contestadas frente a hechas, y los 429.
  - E1 añade la tabla de umbrales, recalculada con `select` sobre las mismas evaluaciones. Usa
    fracciones exactas (1/3, 2/3, 1) para que «0,67» signifique «2 de 3».
- **Parada por 429:** la ejecución se detiene con un informe parcial si los 429 superan el 5 % de
  las peticiones.
- **Tests de la regla de puntuación:** `test_eval_scoring.py` no lleva el marcador y corre en
  `make test`.
- **Techo de recuperación** (comprobado sin llamadas a la API): el SKU aceptable no está en el
  top 10 de la recuperación en q06 (`MT-0020`) ni en q10 (`MT-0017`). En q09 faltan 2 de sus 4.
  Por eso E1–E3 llegan como mucho a 8/10, y el informe lo muestra en la columna `reachable`.

### Línea base (decisión del usuario)

- **Modelo de embeddings:** E1–E3 se ejecutan con el modelo actual,
  `paraphrase-multilingual-MiniLM-L12-v2`. Es multilingüe; se comprobó en la configuración, en el
  Dockerfile y en el catálogo de fastembed.
- **Dataset:** no cambia.
- **Informe:** da dos números.
  - **Extremo a extremo:** aciertos sobre 10, junto al techo de recuperación (8/10: en q06 y q10
    no hay ningún SKU aceptable entre los candidatos).
  - **Solo selector:** aciertos contando únicamente las preguntas que tienen un SKU aceptable entre
    los candidatos.
- **Cambio de modelo:** queda como PR 4b del plan, y se decidirá con estos datos.
- **Ejecución pendiente:** el primer intento se paró en la primera tanda de peticiones: la API
  respondió 400 por falta de crédito. Ninguna de esas peticiones se facturó. Se repite cuando haya
  crédito.

## Correcciones tras la code review (3b)

La revisión (`/code-review`, lanzada por el usuario) dio 10 hallazgos y se comprobó cada uno contra el
código. Estas son las decisiones del usuario:

| # | Qué | Por qué | Criterio |
|---|---|---|---|
| RB1 (#1) | El agente solo se construye en modo `agent` | En `rag` se construían el evaluador, el selector y el grafo para nada, y un fallo de configuración del agente rompía `rag` | En modo `rag` no se llama a `get_catalog_agent` |
| RB2 (#3) | Si el agente falla después de ejecutar el selector, el fallback conserva `recommendation`, reutiliza las `sources` ya recuperadas y el error lleva el uso acumulado hasta el fallo (como CR4) | B10: `recommendation` es un objeto siempre que el selector se ejecutó. Además se evita una recuperación repetida. | Test: el selector elige X, el siguiente turno da 529 → respuesta con `fallback_used=true`, `recommendation` = X y el uso registrado |
| RB3 (#4) | `find_by_sku(sku, embedding)` devuelve la **similitud coseno real** contra el embedding de la pregunta, en la misma consulta. El producto entra en `sources`, y si ya estaba se conserva la entrada existente. **La pregunta se embebe una vez por petición** y se reutiliza en las herramientas. | `score` mantiene un único significado en todas las `sources` sin inventar valores | Tests del adaptador y de la herramienta |
| RB4 (#5) | Si el modelo termina con `max_tokens` o `refusal`: razón de parada nueva, **`model_incomplete`**, con el `stop_reason` original. Se responde con el **fallback RAG determinista** (`fallback_used=true`). Queda en el DTO y en el log, no en la API. **No** se usa `LLMUnavailableError`, que significa fallo transitorio. **El modo `rag` se comporta igual.** | Hoy, en los dos modos, una respuesta cortada o una negativa salen como una respuesta normal con 200 (comprobado: `AnthropicLLMClient` ignora `stop_reason`) | Tests en los dos modos: `max_tokens` → fallback; `refusal` → fallback; y la razón queda en el DTO |
| RB5 (#8) | `usage.model` es el modelo que devuelve la API, también en modo `agent` | En `rag` ya era así; en `agent` era el nombre configurado | Test del agente |
| RB6 (#9) | Una sola llamada a `messages.create` con `omit` cuando no hay herramientas, en un **commit de refactor aparte** | Elimina la duplicación del `if/else` | Los tests existentes siguen en verde |
| Aplazado (#7) | Herramientas del mismo turno en paralelo | Se decide cuando las evals midan la latencia. Si se hace, **el límite de concurrencia de llamadas debe compartirse por petición**, para que dos `recommend_candidate` en paralelo no dupliquen el presupuesto. | — |

**Sin cambios:**
- **#2 (overrides de `get_catalog_agent`):** es el mismo patrón que `get_llm_client`, y deja de importar con RB1.
- **#6 (cerrar el cliente con varias apps en el mismo proceso):** no ocurre en producción, y en los tests secuenciales las cachés se limpian al cerrar.
- **#10 (docstrings en los puertos):** falso positivo. El `CLAUDE.md` del repo los permite en los puertos.

**Ajuste de B3:** el comportamiento de `rag` solo cambia en una cosa (RB4). Una respuesta cortada por
`max_tokens` o una negativa ya no salen como una respuesta normal, sino como el fallback determinista.

### Cómo se implementaron (commit 3)

- **RB1:** el nuevo proveedor `get_mode_catalog_agent` depende de `get_assistant_mode` y solo llama a
  `get_catalog_agent()` en modo `agent`. En `rag` devuelve `None`. `get_ask_assistant_use_case`
  depende de él. Por eso los e2e del modo `agent` sobrescriben `get_mode_catalog_agent` en lugar de
  `get_catalog_agent` y `get_assistant_mode`.
- **RB2:** el error `AgentUnavailableError(LLMUnavailableError)` lleva `sources`, `recommendation` y
  `usage`.
  - Vive en `domain/agent.py`, junto a `AgentResult`. En `domain/exceptions.py` creaba un ciclo de
    imports: `agent → selection → candidate → exceptions → agent`.
  - Los nodos `model` y `rag_answer` envuelven el fallo transitorio con el estado de ese momento, y
    `run()` construye el error con el uso acumulado.
  - El log es la misma línea `agent_run`, con `stop_reason=unavailable`. Ese valor solo aparece en
    el log.
  - `AskAssistant` reutiliza las `sources` del error y solo recupera si vienen vacías, por ejemplo
    cuando falla el primer turno.
- **RB3:**
  - La pregunta se embebe una vez al principio de `run()` y viaja en `ToolContext.question_embedding`.
  - `find_by_sku` calcula la distancia `<=>` en la misma consulta.
  - `IndexedProduct` desaparece: el puerto devuelve `RetrievedDocument`.
- **RB4:**
  - `INCOMPLETE_STOP_REASONS = {"max_tokens", "refusal"}`, en `domain/completion.py`.
  - `Completion` y `ModelTurn` exponen el `stop_reason` de la API.
  - Un turno incompleto no ejecuta sus herramientas.
  - `AnswerDTO.model_stop_reason` y el campo `model_stop_reason` del log guardan la razón.
  - El texto OpenAPI de `fallback_used` y el README describen el nuevo caso.
- **RB5:** el estado del grafo guarda el `model` del último turno. Si ningún turno respondió, se usa
  el nombre configurado.

Evidencia (rojo → verde):

- **Rojo:** con el código sin modificar fallaban las 17 pruebas RB.
  - Las de `test_ask_assistant.py`, `test_agent_tools.py` y `test_langgraph_catalog_agent.py`, en la
    recolección: `ImportError: cannot import name 'AgentUnavailableError'` y
    `TypeError: ToolContext.__init__() got an unexpected keyword argument 'question_embedding'`.
  - `test_rb1_rag_mode_never_builds_the_agent`, con `assert 1 == 0` en `currsize`.
  - Las de los adaptadores: `'ModelTurn' object has no attribute 'stop_reason'`,
    `'Completion' object has no attribute 'stop_reason'` y
    `find_by_sku() takes 2 positional arguments but 3 were given`.
- **Verde:** pasan las 17 pruebas RB, `make lint` (ruff, pylint 10.00/10 y mypy sin incidencias) y
  `make test` (252 pruebas).

## Evidencia

_Se completa al terminar._
