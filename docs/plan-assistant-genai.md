# Plan — Assistant: IA generativa sobre el catálogo (puerto LLM → RAG → selección de candidatos → agente → despliegue → evaluador jev)

Bounded context: `assistant`. Arquitectura: DDD + Hexagonal (según `CLAUDE.md`).

Objetivo: responder preguntas en lenguaje natural sobre el catálogo, tratando el LLM, los
embeddings y el framework de agentes como **adaptadores detrás de puertos**. El dominio nunca
importa `anthropic`, `langgraph` ni `pgvector`.

Se entrega en seis PR (el PR 3 se divide en 3a y 3b). Cada uno se puede publicar por sí solo y mantiene el CI en verde.

## Decisiones tomadas

- **Proveedor LLM**: Anthropic (SDK `anthropic`, `AsyncAnthropic`). Modelo y timeout salen de los
  settings; por defecto, el modelo de Claude más barato para desarrollo.
- **Almacén vectorial**: `pgvector` dentro del Postgres existente. Sin infraestructura nueva.
- **Embeddings**: detrás del puerto `EmbeddingClient`. Adaptador para desarrollo y CI: `fastembed`
  (modelo ONNX local, sin API key y sin coste) con
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones, ~50 idiomas:
  funcionan preguntas en español y en inglés). Más adelante se puede añadir un adaptador alojado
  (p. ej. Voyage AI) sin tocar el dominio.
- **Framework de agentes**: LangGraph, confinado en `infrastructure/agent/`.
- **Regla entre contextos**: `assistant` nunca importa `catalog.domain`. Mantiene su propio read
  model (`product_documents`), alimentado mediante DTOs.
- **Los tests unitarios nunca llaman a un modelo real**: `FakeLLMClient` / `FakeEmbeddingClient` en
  el límite del puerto, con el mismo patrón que `FakeProductRepository`.
- **Cuando el LLM falla**: el PR 1 responde 503 (todavía no hay nada que recuperar). Desde el PR 2,
  una respuesta de fallback determinista (los resultados top-k sin generación) con
  `fallback_used=true`.
- **Disparador del indexado: reindexado bajo demanda.** `assistant` tiene un caso de uso
  `IndexCatalog` que lee los productos a través de su propio puerto `CatalogReader` (solo DTOs) y
  actualiza `product_documents`. `catalog` no cambia y no sabe que `assistant` existe. Solo se
  ejecuta con `make reindex`: no hay endpoint público mientras la API no tenga autenticación.
  Compromiso aceptado: el índice queda desactualizado hasta el siguiente reindexado.
  - *Descartado — síncrono dentro de `CreateProduct` / `UpdateProduct`*: haría que `catalog`
    dependiera de `assistant` y cargaría la latencia de los embeddings en cada escritura.
  - *Evolución futura (no entra en el PR 2)*: `catalog` publica los eventos de dominio
    `ProductCreated` / `ProductUpdated` / `ProductDeleted` mediante un **outbox** transaccional;
    `assistant` los consume y reindexa solo lo que cambió. Necesita un mecanismo de eventos/outbox
    que el repo todavía no tiene.

---

## PR 1 — Puerto `LLMClient` + caso de uso `AskAssistant` (todavía sin RAG)

### Dominio — `src/contexts/assistant/domain/`

- `ports/llm_client.py` — ABC `LLMClient`:
  `async complete(*, system: str, prompt: str, max_tokens: int) -> Completion`.
- `completion.py` — dataclass inmutable `Completion`: `text`, `model`, `input_tokens`,
  `output_tokens`, `latency_ms`.
- `exceptions.py` — `InvalidQuestionError(InvalidInputError)`,
  `LLMUnavailableError(ServiceUnavailableError)`.
- `question.py` — value object `Question`: no vacío, longitud máxima (p. ej. 1.000 caracteres),
  sin espacios en los extremos.

### Aplicación — `src/contexts/assistant/application/`

- `dtos.py` — `AskCommand(question: str)`, `AnswerDTO(text, usage)`, `UsageDTO(model, input_tokens,
  output_tokens, latency_ms)`.
- `use_cases/ask_assistant.py` — construye el prompt, llama a `LLMClient` y convierte `Completion`
  en `AnswerDTO`. `LLMUnavailableError` se propaga.

### Infraestructura — `src/contexts/assistant/infrastructure/`

- `llm/anthropic_llm_client.py` — `AnthropicLLMClient(LLMClient)`; envuelve `AsyncAnthropic`, fija
  timeout y reintentos una sola vez al construirse, mide la latencia y lee el uso de tokens de la
  respuesta. Los errores transitorios del SDK (conexión, timeout, 429, 5xx) pasan a
  `LLMUnavailableError`; los de configuración (400/401/403/404) se propagan sin cambios (500).

### UI — `src/contexts/assistant/ui/`

- `schemas.py` — `AskRequest`, `AnswerResponse` (Pydantic, `extra="forbid"`).
- `routers/assistant.py` — `POST /assistant/ask`, tag `assistant`.
- `dependencies.py` — cableado de dependencias del contexto.

### Shared

- `domain/errors.py` — `ServiceUnavailableError(DomainError)`.
- `infrastructure/exception_handlers.py` — convierte `ServiceUnavailableError` en 503.
- `settings.py` — `anthropic_api_key: SecretStr | None`, `llm_model: str`, `llm_timeout_s: float`
  (por intento), `llm_max_retries: int` (0 por defecto), `llm_max_tokens: int`.
- `.env.example` — las variables nuevas, con la clave vacía.
- `pyproject.toml` — añadir `anthropic`.

### Tests

- `tests/fakes/llm_client.py` — `FakeLLMClient`, compartido por los tests unitarios y los e2e.
- `tests/integration/contexts/assistant/` — el adaptador contra `httpx2.MockTransport`:
  clasificación de errores y un único intento con `max_retries=0`.
- `tests/e2e/test_exception_handlers.py` — cada error de dominio compartido devuelve su código de
  estado.
- `tests/unit/contexts/assistant/` — tests de las invariantes de `Question`, del caso feliz, del uso
  propagado al DTO y de `LLMUnavailableError` propagado cuando el fake falla.
- `tests/e2e/test_assistant.py` — sustituye la dependencia `LLMClient` por el fake: 200, 422 con la
  pregunta vacía y 503 cuando el fake falla.

---

## PR 2 — RAG con pgvector

- `docker-compose.yml` — `db` y `db-test` pasan a `pgvector/pgvector:pg16`.
- Migración de Alembic — `CREATE EXTENSION IF NOT EXISTS vector`; tabla `product_documents`
  (`product_id UUID PK`, `content TEXT`, `content_hash TEXT`, `embedding vector(384)`,
  `updated_at`), índice HNSW sobre `embedding` (coseno).
- Puertos de dominio —
  - `EmbeddingClient.embed(texts) -> list[list[float]]`.
  - `DocumentSearch.search(embedding, k) -> list[RetrievedDocument]`.
  - `DocumentIndex`: leer el `product_id → content_hash` guardado, hacer upsert de documentos y
    borrar documentos por `product_id`.
  - `CatalogReader.read_all() -> list[CatalogProduct]` — la vista propia de `assistant` sobre un
    producto, no el DTO de `catalog`. `CatalogReader.missing(ids)` confirma qué ids ya no existen
    de verdad (la paginación no es consistente con una instantánea, así que no aparecer en
    `read_all` no prueba que se haya borrado).
  - `EmbeddingClient.model_name` — forma parte del `content_hash`, así que cambiar de modelo vuelve
    a calcular los embeddings.
- Aplicación —
  - Caso de uso `IndexCatalog`, **incremental**: construye el contenido del documento de cada
    producto y su `content_hash`; calcula embeddings y hace upsert solo de los productos nuevos o
    cambiados (`Product` no tiene `updated_at`, así que el hash —sobre modelo + contenido— es lo
    que detecta los cambios), en lotes de 256. **Borra los documentos huérfanos** solo después de
    que `CatalogReader.missing` confirme que el producto ya no existe. Devuelve los recuentos
    (indexados, sin cambios, borrados).
  - `AskAssistant` ahora calcula el embedding de la pregunta, recupera el top-k, lo pone en el
    prompt y lo devuelve como `sources`. `AnswerDTO` gana `sources` y `fallback_used`.
- Fallback — `AskAssistant` captura `LLMUnavailableError` y devuelve los resultados top-k sin
  generación, con `fallback_used=true` y 200. El 503 del PR 1 deja de llegar al cliente.
- Infraestructura —
  - `FastEmbedEmbeddingClient` (modelo, directorio de caché y `local_files_only` desde los
    settings). El `Dockerfile` descarga el modelo al construir la imagen; en ejecución solo se carga
    de disco y se calienta en el lifespan de la app.
  - `SqlAlchemyDocumentSearch` (con su propia sesión corta, para no retener ninguna conexión durante
    la llamada al LLM) / `SqlAlchemyDocumentIndex` (`pgvector.sqlalchemy.Vector`). `RAG_TOP_K` ≤ 40
    (el `ef_search` por defecto de HNSW).
  - Adaptador de `CatalogReader`: el **único** sitio donde `assistant` toca `catalog`. Llama a la
    API pública de aplicación de `catalog` (`ListProducts`, paginado; `GetProduct` para confirmar
    bajas) y convierte `ProductDTO` en `CatalogProduct`. Nunca `catalog.domain` ni
    `catalog.infrastructure`.
- UI (adaptadores de entrada) —
  - `ui/cli/reindex.py` — punto de entrada `python -m contexts.assistant.ui.cli.reindex`. Construye
    `IndexCatalog` con los **mismos proveedores de dependencias** que la API (`ui/dependencies.py`,
    `shared/infrastructure/database.py`), lo ejecuta e imprime los recuentos. Es un adaptador de
    entrada igual que el router, reutilizable como `Job` de Kubernetes en el PR 4.
  - `Makefile` — `make reindex` ejecuta ese módulo en el contenedor `api`.
  - Sin endpoint HTTP para el indexado.
- `pyproject.toml` — añadir `pgvector` y `fastembed`.
- Tests —
  - Unitarios con fakes: indexado incremental (los productos sin cambios no recalculan su
    embedding), **borrado de huérfanos**, recuperación en `AskAssistant` y fallback cuando el LLM
    falso falla.
  - Integración contra el `db-test` real: adaptador de búsqueda (se siembran tres documentos y se
    comprueba que vuelve primero el más cercano) y adaptador del índice (upsert, hashes, borrado).
  - Los e2e comprueban el indicador de fallback en lugar del 503.
- README — marcar el paso 2 del roadmap como hecho y sustituir «`assistant` never imports
  `catalog`» por la regla real (solo el adaptador `CatalogReader`, a través de la API de aplicación
  de `catalog`).

---

## PR 3a — Read model y selección de candidatos

Sin punto de entrada todavía: `RecommendCandidate` solo lo ejercitan sus tests hasta que el PR 3b
añade la herramienta del agente. No cambia ningún comportamiento existente.

- **Read model** — una migración añade `sku` (índice único), `name` y el precio (`price_cents`,
  `currency`) como columnas de `product_documents`. Las rellena `IndexCatalog` desde el DTO del
  catálogo; `catalog` no cambia. Las filas con alguna de estas columnas a nulo cuentan como
  cambiadas, así que el reindexado incremental las rellena (con test). `get_product_by_sku` lee la
  columna `sku`; la respuesta sin recomendación lista nombre, SKU y precio.
  - **Orden en `IndexCatalog`**: los huérfanos confirmados se borran **antes** del upsert. Si no, un
    producto borrado y otro nuevo con el mismo SKU entre dos reindexados harían chocar el upsert con
    el índice único, y todo el reindexado haría rollback. Lo cubre un test que reproduce ese caso.

### Selección de candidatos

**Objetivo** — tras la recuperación, se puede recomendar un producto de entre los
candidatos top-k para preguntas como *«¿cuál de estos me recomiendas para X?»*, o declinar
explícitamente la recomendación.

**Principio de diseño — el modelo lee, el código decide.** Es una decisión de diseño de este
proyecto, no una recomendación externa.

- **Cada candidato se evalúa por separado, nunca todos en una sola pregunta.** Elegir entre varios
  elementos en una sola pregunta puede depender del orden en que se presentan; evaluar cada uno por
  separado, en paralelo, y ordenar en código elimina esa dependencia. La **eval de invariancia al
  orden** (PR 3b) es la que comprueba que se cumple.
- Cada evaluación son unas pocas preguntas pequeñas de sí/no (`noul`), un juicio cada una, con un
  significado explícito para sí y para no.
- El filtrado, la ordenación y los umbrales viven en el código, nunca en el modelo.
- El estado que se envía por candidato contiene solo lo que necesitan las preguntas.

**Rúbrica** (definida una vez, en código; todos los evaluadores la usan sin cambios)

| Id | Pregunta (`noul`) | Papel |
|---|---|---|
| `meets_requirements` | «¿Cumple los requisitos explícitos de la pregunta?». Criterio: sí si cumple todos los requisitos que la pregunta enuncia explícitamente; **si la pregunta no enuncia requisitos explícitos, se responde sí**. | **Filtro.** Se excluyen los candidatos cuya probabilidad queda por debajo de `selector_requirements_threshold`. |
| `suitable_for_use` | «¿Sirve para el uso X?», siendo X el uso por el que pregunta la pregunta. | **Ordenación.** Los candidatos que quedan se ordenan solo por esta probabilidad. Sin pesos. |

Sin preguntas `score`: la expectativa de `score` no está calibrada entre niveles, así que nunca
entra en una ordenación. Los números (precios, tamaños) nunca se le preguntan al modelo; cuando
hace falta, se calculan en código.

**Dominio**

- `Candidate` — `product_id`, `sku`, `name`, `price_cents`, `currency`, `content` (el texto del
  documento indexado) y `retrieval_score`. El catálogo no tiene descripción de producto, así que el
  texto del candidato es el `content` del documento.
- `Assessment` — `product_id`, la probabilidad de sí de cada pregunta de la rúbrica
  (`meets_requirements`, `suitable_for_use`), o `None` si ese candidato no se pudo evaluar.
- `Selection` — `product_id` elegido o `None`, `score` (la probabilidad de `suitable_for_use` del
  elegido), `fallback_used`, `reason`: `chosen` | `below_threshold` | `no_assessments`.
- Puerto `CandidateAssessor.assess(question, candidate) -> Assessment`. Su docstring fija el
  contrato: un candidato por llamada, nunca ve a los demás candidatos, las respuestas son
  probabilidades en `[0, 1]` y solo lanza `LLMUnavailableError` ante fallos transitorios.
- `select(candidates, assessments, requirements_threshold, min_score) -> Selection` — función
  pura. Recibe también los candidatos porque el desempate usa su `retrieval_score` y porque solo
  puede devolver uno de ellos:
  - descarta los candidatos que no se pudieron evaluar;
  - se queda con los que tienen `meets_requirements >= requirements_threshold`;
  - ordena el resto por `suitable_for_use`, de mayor a menor. Los **empates** los gana el de mayor
    `retrieval_score`; si también empatan, el de menor `product_id`, para que la elección sea
    siempre determinista;
  - recomienda el primero si su `suitable_for_use >= min_score`; si no, `None`.

  Las dos comparaciones son **mayor o igual**. Con 3 muestras las probabilidades posibles son 0;
  0,33; 0,67 y 1, así que un umbral de 0,5 equivale a «mayoría sí» (2 de 3).

**Aplicación**

- Caso de uso `RecommendCandidate`: recibe los candidatos de la recuperación y solo pasa al
  evaluador los **`selector_top_n`** primeros (10 por defecto). En el PR 3b, el agente pide
  `selector_top_n` resultados al recomendar. Es independiente de `rag_top_k`, que sigue siendo la
  cantidad de contexto que recibe el LLM para responder. El caso de uso lanza la evaluación de todos
  los candidatos a la vez, con un plazo global `selector_timeout_s` = 10 s, y después llama a
  `select`. El límite de concurrencia (`selector_max_concurrency` = 10) se aplica **por llamada a la
  API** dentro del evaluador: las muestras de un candidato salen juntas, así que los candidatos van
  terminando uno tras otro y un plazo corto deja sin evaluar solo a algunos, no a todos.
- **Un candidato solo participa con todas sus muestras válidas.** Una muestra inválida (incluida una
  respuesta cortada por `max_tokens`), fallida o que no llega a tiempo lo deja sin evaluar, y el log
  registra la razón (`invalid_sample`, `error`, `deadline`). Si se cancela la petición, se cancelan
  todas las evaluaciones; un error de configuración se propaga en el acto.
- Un fallo transitorio sigue lanzando `LLMUnavailableError`, como subclase
  `AssessmentUnavailableError` que lleva el uso acumulado, para que el log no pierda los tokens de
  las muestras que sí respondieron.
- Si no se pudo evaluar ningún candidato: fallback determinista — los candidatos ordenados por
  `retrieval_score`, sin recomendación (`fallback_used = true`).

**Infraestructura**

- `ClaudeCandidateAssessor` — el único evaluador de este PR. Es un adaptador, así que **habla con el
  SDK de Anthropic directamente**, con salida estructurada, y **reutiliza la clasificación de
  errores del PR 1**; el puerto `LLMClient` no cambia. Claude no devuelve probabilidades, así que la
  probabilidad de cada respuesta sale de la **self-consistency**: se pregunta la rúbrica
  `selector_samples` veces (**3** por defecto: impar, para que sí y no no puedan empatar), con las
  dos preguntas de la rúbrica en la misma llamada y un sí/no para cada una, y se usa la
  **frecuencia del sí** como probabilidad. No se usa la confianza que declara el propio modelo. Las
  muestras usan el muestreo por defecto del modelo (la Messages API actual rechaza `temperature` /
  `top_p` / `top_k`).
- Las preguntas de la rúbrica se definen en código, no en prompts repartidos por los adaptadores,
  para que un segundo evaluador (PR 5) las reutilice sin cambios.

**Settings** — `selector_provider` (por ahora solo `claude`; el PR 5 añade `jev`), `selector_top_n`
(10 por defecto), `selector_max_concurrency` (10), `selector_timeout_s` (10),
`selector_samples` (3), `selector_max_tokens` (1024), `selector_requirements_threshold` (0,5) y
`selector_min_score` (0,5). Las evals fijan los valores finales de los umbrales. El evaluador usa
`effort: "low"` y no desactiva el razonamiento, porque `thinking: disabled` devuelve 400 en
`claude-opus-5-5` y `claude-sonnet-5-5`.

**Presupuesto de llamadas** — `selector_top_n × selector_samples` = 10 × 3 = **30 llamadas a
Claude** por recomendación; con 10 en paralelo son unas tres rondas (~3 s), muy por debajo del
plazo de 10 s. Una ráfaga de 30 llamadas puede chocar con un límite bajo de Anthropic: un `429` es
transitorio según la clasificación del PR 1, así que ese candidato queda sin evaluar y la selección
se hace con el resto.

**Log** — una línea por selección: proveedor, id del modelo, **llamadas hechas y llamadas
contestadas** (para que las evals detecten `429` y timeouts), latencia, tokens, coste y la razón
(`chosen`, `below_threshold`, `no_assessments`). Nunca datos de producto más allá de los ids.

**Tests unitarios** (`CandidateAssessor` falso; para el adaptador de self-consistency, el cliente
de Anthropic sobre `httpx2.MockTransport` con respuestas guionizadas, como en el PR 1)

- Gana el mayor `suitable_for_use`; en un empate, el de mayor `retrieval_score`; en un doble
  empate, el de menor `product_id`.
- Un candidato por debajo de `requirements_threshold` queda excluido aunque sea el mejor ordenado.
- Sin requisitos explícitos → `meets_requirements` es sí y no filtra nada.
- Todos por debajo de `min_score` → sin recomendación; justo en `min_score` (o en
  `requirements_threshold`) pasa (`>=`).
- Falla un candidato → se elige entre el resto.
- Fallan todos → fallback determinista por `retrieval_score`.
- Entrada barajada → misma selección.
- Nunca se devuelve un producto que no esté entre los candidatos.
- Self-consistency (3 muestras): 3 de 3 sí → 1,0; 2 de 3 → 0,67; 1 de 3 → 0,33; una muestra
  inválida o cortada por `max_tokens` deja el candidato sin evaluar.
- Solo el top `selector_top_n` de la recuperación llega al evaluador.

**Decidido** (con el usuario): rúbrica de dos preguntas con un filtro de requisitos y ordenación
solo por idoneidad (sin pesos); la puntuación es la probabilidad de «sirve para X»;
self-consistency para Claude con 3 muestras; desempate por `retrieval_score` (y después por
`product_id`); los dos umbrales a 0,5 con `>=`; el agente pide `selector_top_n` resultados al
recomendar, separado de `rag_top_k`; 10 en paralelo, plazo de 10 s, top 10 al selector; llamadas
contestadas registradas por selección; sin pregunta de seguimiento; `score` nunca en una
ordenación; el principio de diseño registrado como decisión de este proyecto; `name` como columna
igual que `sku` y el precio; el `content` del documento en lugar de `description`; huérfanos
borrados antes del upsert; `ClaudeCandidateAssessor` directo sobre el SDK; errores del LLM del
agente traducidos con la misma clasificación.

---

## PR 3b — Agente con LangGraph

Se apoya en el PR 3a: usa `RecommendCandidate`, el read model con `sku`, `name` y precio, y la
rúbrica.

- Puerto de dominio — `CatalogAgent.run(question) -> AgentResult` (respuesta, llamadas a
  herramientas hechas, uso).
- Infraestructura — `infrastructure/agent/langgraph_catalog_agent.py`: un grafo pequeño con las
  herramientas `semantic_search` (usa `DocumentSearch`), `get_product_by_sku` (lee el read model) y
  `recommend_candidate` (más abajo), y después un nodo de respuesta final.
  - **LangGraph solo orquesta.** El nodo del modelo llama al SDK de Anthropic directamente
    (tool use) a través de nuestro adaptador en `infrastructure/agent/`, reutilizando **el único
    cliente** del asistente y **la clasificación de errores del PR 1**. No se usa `langchain-anthropic`:
    su última versión (1.7.6) exige `anthropic<2.0.0` y el proyecto usa 2.3.0.
  - **Cada herramienta se define una vez** (esquema + handler); de esa definición se derivan tanto las
    definiciones de herramientas que se envían a la API como el nodo de herramientas del grafo.
- Límites — **como mucho 5 llamadas a herramientas por ejecución** (`recommend_candidate` cuenta
  como una), con **un contador en el estado del grafo y una arista condicional** que, al llegar al
  límite, pasa a responder en modo RAG con lo recuperado y registra la razón `max_steps`.
  `recursion_limit` queda solo como red de seguridad. Lista blanca de herramientas, el mismo timeout que el PR 1 y el mismo fallback
  que el PR 2, con el uso de tokens sumado entre pasos.
- `AskAssistant` delega en el agente según un setting (`assistant_mode = "rag" | "agent"`), **`rag`
  por defecto**: el agente es opt-in hasta que las evals demuestren que es mejor. El comportamiento en
  `rag` no cambia; los e2e del PR 2 solo ganan la clave `"recommendation": None` en el diccionario
  esperado, porque el contrato ganó un campo aditivo.
- Dependencias — los proveedores de `RecommendCandidate` y del evaluador se añaden aquí (no en 3a),
  reutilizando **el único cliente de Anthropic del asistente**, que se cierra en el lifespan.
- `pyproject.toml` — añadir solo `langgraph` (>= 1.2.18). Comprobado con el resolver: con todas las
  dependencias del proyecto, `anthropic` se queda en 2.3.0 y no entra ningún otro paquete de
  Anthropic.
- **Contrato** — `AnswerResponse` gana un campo opcional y nullable `recommendation:
  {product_id, sku, score, reason} | null`. Es aditivo, así que no rompe a los clientes, y el esquema
  es el mismo en los dos modos. Sus valores salen de la `Selection` del selector, **nunca del texto
  del modelo**.
  - `null` cuando **el selector no se ejecutó**: modo `rag`, o el agente respondió sin recomendar.
  - **Objeto** cuando se ejecutó. `reason` ∈ `chosen` | `below_threshold` | `no_assessments`, y
    `product_id`, `sku` y `score` son no nulos **si y solo si** `reason == "chosen"`. Lo impone un
    validador de Pydantic, con test.
  - Un e2e por modo.
- **Razón de parada del agente** — `answered` | `max_steps`. Es un resultado del agente, no de la
  selección, así que **no va en `recommendation` ni en la API**: va en el DTO del caso de uso (para
  las evals) y en el log.
- Tests — unitarios con un agente falso; un test de integración del cableado del grafo con un modelo
  falso guionizado.

### Herramienta `recommend_candidate`

**Agente** — herramienta nueva de LangGraph `recommend_candidate`. Si no hay recomendación, el
agente dice explícitamente que no hay una recomendación clara y lista los candidatos top-k (nombre,
SKU y precio). Por ahora, sin pregunta de seguimiento.

### Evals (marker `eval`, fuera del CI por defecto)

Necesitan la `ANTHROPIC_API_KEY` real, que el usuario ya ha puesto en `.env`. Su valor nunca aparece
en logs, salidas de comandos, documentos ni mensajes de commit. **Antes de la primera ejecución real
se informa del número de llamadas y del modelo**, y se espera.

**Dataset** (lo propone Claude Code y lo revisa el usuario antes de cualquier ejecución real):

- Un catálogo ficticio de material de montaña (cualquier dominio salvo viajes), unos 20 productos, y
  unas 10 preguntas.
- Las preguntas describen **el uso**, sin reutilizar la redacción de las descripciones de producto.
- Incluye productos casi idénticos que solo se diferencian en un requisito explícito (color,
  talla), preguntas cuya respuesta correcta es **no recomendar**, y al menos una pregunta
  **ambigua**.
- Cada pregunta tiene un **conjunto de SKUs aceptables**, no uno solo.
- Versionado en `tests/evals/` y cargado de forma determinista en **su propia base de datos**,
  nunca en los datos del usuario.
- Los resultados se informan como **recuentos** («8/10»), no como porcentajes. Las evals comparan
  `recommendation.sku` con los SKUs aceptables.

- Dataset de preguntas con el SKU esperado.
- Precisión y cobertura (con qué frecuencia recomienda) para varios valores de `selector_min_score`
  y `selector_requirements_threshold`; los umbrales se eligen a partir de esa tabla.
- **Invariancia al orden**: se barajan los candidatos y la recomendación no debe cambiar. Es la
  comprobación del principio de diseño.
- Consistencia al repetir: se pregunta dos veces y la recomendación no debe cambiar.
- Latencia y coste por selección, y llamadas contestadas frente a llamadas hechas.
- `tests/evals/` + marker `eval` — ~10 preguntas con el SKU esperado; informa del porcentaje de
  aciertos y del coste del agente completo. Se ejecuta a mano con la clave real: `make eval`.

---

## PR 4 — Despliegue

- `k8s/` — `Deployment` (liveness en `/healthz`), `Service`, `ConfigMap`, `Secret` (solo plantilla),
  `Job` que ejecuta `alembic upgrade head`, `Job` que ejecuta
  `python -m contexts.assistant.ui.cli.reindex` y Postgres con pgvector para uso local.
- `make k8s-up` / `make k8s-down` — se ejecuta en `kind` en local.
- CI — job opcional que crea un clúster kind, aplica los manifiestos y llama a `/healthz`.
- Opcional — la misma imagen en AWS (App Runner o ECS Fargate + RDS con pgvector).

---

## PR 5 — Evaluador jev

Añade un segundo `CandidateAssessor` sobre un modelo de decisión. Nada fuera del adaptador cambia:
el puerto, `select`, `RecommendCandidate` y la rúbrica vienen del PR 3a; la herramienta del agente,
del PR 3b.

**Proveedor — Decisions API de OpenRouter** (decidido), con `httpx` directo.

- `JevCandidateAssessor` — `POST {jev_base_url}/alpha/decisions`
  (`https://openrouter.ai/api/alpha/decisions`), `Authorization: Bearer <API key de OpenRouter>`.
  Una petición por candidato: `{model, state, questions}`, con `questions` indexado por el id de la
  rúbrica. Las dos preguntas de la rúbrica van en la misma petición, como dos preguntas `noul`. jev
  devuelve directamente la probabilidad de cada `noul`, así que este evaluador **no necesita
  self-consistency**: `selector_samples` solo se aplica a `ClaudeCandidateAssessor`.
- **Reglas de la petición** (OpenAPI): toda pregunta necesita `type` e `instructions`.
  `noul.criteria`, si se envía, debe llevar exactamente `true` y `false`. `choice.criteria` es un
  mapa de opciones obligatorio. `score.criteria` es una lista ordenada obligatoria con al menos un
  nivel. `state` es un texto, un objeto o un array.
- **Respuesta**: `{id?, model, provider?, answers, usage{input_tokens, output_tokens, cost?}}`, una
  respuesta por cada clave pedida. `noul` solo trae su probabilidad (sin `confidence`); `choice` y
  `score` pueden añadir `probabilities` y `confidence`, y `score` puede añadir `legend`.
  - **Parseo estricto**: se comprueba el `type` de cada respuesta. Una clave que falta o un `type`
    inesperado deja el `Assessment` de ese candidato en `None`. Los campos opcionales
    (`probabilities`, `confidence`, `legend`, `usage.cost`) se leen comprobando su presencia.
- **Clasificación de errores** (la misma regla que `AnthropicLLMClient` en el PR 1):
  - Transitorios → `LLMUnavailableError`: errores de conexión, timeouts, `429`, `500`, `502`,
    `503`, `524` (timeout en el borde de la red) y `529` (proveedor sobrecargado).
  - De configuración o de la cuenta → se propagan (500) con una línea de log clara: `400`, `401`,
    `402` (créditos insuficientes: reintentar no lo arregla), `403`, `404` y `413`.
- **Modelo fijado al build con fecha** `typesafe/jev-1.14-20261014` (el `canonical_slug` del
  catálogo en vivo; la referencia de OpenRouter dice que las peticiones lo aceptan). Nunca el alias
  `~typesafe/jev-latest`. Se registran en el log el `model` que devuelve cada respuesta (el build
  exacto que respondió) y `usage.cost` (USD).
- **Privacidad**: se envían las preferencias de proveedor `zdr: true` y `data_collection: "deny"`.
  El catálogo no tiene datos personales, pero es buena práctica. El OpenAPI define las dos; la guía
  de jev no dice si jev las admite, así que **hay que comprobarlo con la primera petición real** (una
  preferencia no admitida devuelve un error).
- **Tamaño del estado**: cada petición debe quedar muy por debajo de ~32.000 bytes de texto. Por
  encima, TypeSafe pasa a su modo de contexto largo, que describe como más lento y menos preciso.
  Una petición por candidato con solo la pregunta y el texto del candidato queda muy lejos de ese
  límite.
- **Endpoint alpha, totalmente aislado en este adaptador**: nada fuera de él conoce la ruta, el
  payload ni la forma de la respuesta. Pasar a TypeSafe directo (`POST
  https://api.typesafe.ai/v1/systemone`, con el id del modelo sin prefijo) es un cambio de settings
  más este adaptador. Queda registrado como riesgo conocido en el documento del paso.

**Settings** — `selector_provider` gana `jev`. Nuevos: `jev_model` (build con fecha),
`jev_base_url` (`https://openrouter.ai/api` por defecto) y `jev_api_key: SecretStr | None` (la API
key de OpenRouter).

**Evals** — jev frente a Claude sobre el dataset del PR 3b: precisión y cobertura por umbral,
invariancia al orden, consistencia al repetir, latencia y coste por selección. **Los umbrales se
eligen de nuevo para cada modelo**: las probabilidades cambian entre modelos para la misma
pregunta. Otros modelos de decisión sobre la misma Decisions API (22 de 13 fabricantes a
16-10-2026) se pueden comparar cambiando solo `model`.

**Antes de escribir el adaptador** — confirmar el contrato en las fuentes oficiales. Si algo difiere
de este plan, avisar en lugar de adaptarlo en silencio. Fuentes:

- Guía de jev en OpenRouter: `https://openrouter.ai/docs/guides/community/jev.md`
- Referencia de la Decisions API (OpenAPI):
  `https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request.md`
- Catálogo en vivo: `GET https://openrouter.ai/api/v1/models?output_modalities=decisions`
- Documentación de TypeSafe: `https://docs.typesafe.ai` («How to build with System One»,
  «Confidence»)

---

## Criterio de «hecho»

- `make lint` y `make test` en verde; mypy strict pasa sobre el contexto nuevo.
- README actualizado: la sección de arquitectura menciona el contexto `assistant`; descripción y
  topics del repo puestos (`fastapi`, `ddd`, `hexagonal-architecture`, `rag`, `pgvector`,
  `langgraph`).
