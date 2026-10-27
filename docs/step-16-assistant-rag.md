# Paso 16 — Contexto `assistant`: RAG con pgvector (PR 2)

Rama `feature/assistant-rag`. Plan: `docs/plan-assistant-genai.md` → «PR 2 — RAG with pgvector».

## Objetivo

Que una pregunta a `POST /assistant/ask` sobre productos del catálogo devuelva una respuesta
basada en esos productos, con los productos usados como `sources`, y que siga respondiendo, con
`fallback_used=true`, aunque el LLM no esté disponible.

## Qué

El asistente responde a partir del catálogo real:

1. **Indexado bajo demanda.** `make reindex` ejecuta el caso de uso `IndexCatalog`, que:
   - lee los productos a través del puerto `CatalogReader`;
   - construye el texto de cada producto y su `content_hash`;
   - calcula embeddings y hace upsert solo de los productos nuevos o cambiados;
   - borra los documentos huérfanos, es decir, los de productos que ya no existen.
2. **Recuperación.** `POST /assistant/ask` calcula el embedding de la pregunta, recupera los k
   documentos más cercanos (`pgvector`, distancia coseno), los incluye en el prompt y los
   devuelve como `sources`.
3. **Fallback.** Si el LLM no está disponible, la respuesta es 200 con los resultados recuperados,
   sin generación, y `fallback_used=true`. Sustituye al 503 del PR 1.

## Por qué

- El PR 1 dejó un LLM que no conoce el catálogo. Este PR es el que convierte el endpoint en un
  asistente sobre los productos.
- Decisiones tomadas con el usuario (detalle en el plan):
  - **Indexado bajo demanda** y no síncrono en `catalog`: `catalog` no cambia y no sabe que
    `assistant` existe.
  - **Solo `make reindex`**, sin endpoint público, porque la API no tiene autenticación.
  - **Incremental con `content_hash`**: `Product` no tiene `updated_at`, así que el hash es lo que
    detecta los cambios y evita recalcular embeddings de lo que no ha cambiado.
  - **El script es un adaptador de entrada.** `python -m contexts.assistant.ui.cli.reindex` usa los
    mismos proveedores de dependencias que la API, y servirá como Job de Kubernetes en el PR 4.
  - **Modelo multilingüe**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, de 384
    dimensiones. Verificado con `fastembed 0.9.1`.
  - **Eventos de dominio + outbox** quedan como evolución futura, fuera de este PR.

## Fuera de alcance

- **Endpoint HTTP de indexado**: no se crea ninguno mientras la API no tenga autenticación.
- **Indexado automático** al crear, editar o borrar productos, por eventos de dominio y outbox:
  queda como evolución futura en el plan. El índice puede quedar desactualizado hasta el
  siguiente `make reindex`.
- **Cambios en `catalog`**: ni una línea.
- **Proveedor de embeddings alojado** (Voyage AI u otro): el puerto lo permite, pero no se añade.
- **Agente / LangGraph y despliegue**: son los PR 3 y 4.
- **Evaluar la calidad de las respuestas**: las evals son del PR 3. Aquí se comprueba que la
  recuperación ordena bien, no la calidad del texto generado.

## Detalles de diseño fijados aquí

| Tema | Decisión | Porqué |
|---|---|---|
| Texto del documento | `sku`, `name`, `price_cents` y `currency` en un formato estable | Es lo que hay en `ProductDTO`. Si el formato es estable, el hash solo cambia cuando cambia el producto. |
| `content_hash` | SHA-256 del texto del documento | Determinista y sin colisiones prácticas. |
| `k` | Setting `rag_top_k`, 5 por defecto | Configurable, igual que el resto de settings del LLM. |
| Caché del modelo | ~~Volumen Docker con nombre~~ → **modelo dentro de la imagen** (R7) | El volumen evitaba descargas repetidas, pero cada contenedor nuevo seguía necesitando red. Ver R7. |
| Lectura del catálogo | Adaptador `CatalogReader` sobre `ListProducts` (API de aplicación de `catalog`), paginado hasta agotar | Es el único punto de contacto con `catalog`, y solo a través de su capa de aplicación y sus DTOs. |
| Índice vacío | `sources=[]`. El LLM responde con lo que sabe, como en el PR 1. En fallback, mensaje fijo. | No inventar resultados. |
| Salida del CLI | Una línea con `indexed=N unchanged=N deleted=N` | Es la evidencia observable del indexado incremental. |

## Criterios de aceptación

| # | Criterio | Cómo se demuestra |
|---|---|---|
| C1 | Con el índice vacío, `make reindex` indexa todos los productos | Ejecución real: `indexed` = número de productos |
| C2 | Una segunda ejecución sin cambios **no recalcula ningún embedding** | Test unitario: el `FakeEmbeddingClient` no recibe llamadas. Ejecución real: `indexed=0 unchanged=N` |
| C3 | Si cambia un producto, solo ese se recalcula | Test unitario |
| C4 | Si un producto desaparece del catálogo, su documento se borra | Test unitario **e** integración contra `db-test` |
| C5 | `catalog` no cambia | `git diff main -- src/contexts/catalog` vacío |
| C6 | `assistant` solo toca `catalog` en el adaptador `CatalogReader` y en su cableado de dependencias | `grep contexts.catalog src/contexts/assistant` |
| C7 | `/assistant/ask` devuelve `sources` y los documentos van en el prompt | Tests unitario y e2e |
| C8 | Si el LLM falla: 200, `fallback_used=true` y `sources` presentes | Tests unitario y e2e |
| C9 | No hay endpoint de indexado | Rutas de OpenAPI: solo `/assistant/ask` en el contexto |
| C10 | La búsqueda devuelve primero el documento más cercano | Integración contra `db-test` con pgvector |
| C11 | Los quality gates y el CI pasan | `make lint`, `make test` y CI de la PR |
| C12 | Plan y README coinciden con el código | Plan actualizado; README con el paso 2 ✅ y la regla real sobre `catalog` |

## Decisiones tomadas durante la implementación

| Tema | Decisión | Porqué |
|---|---|---|
| Contrato de `CatalogReader` | `read_all` garantiza «sin duplicados», y `missing(ids)` confirma las bajas (R1) | `catalog` solo expone paginación por `offset` ordenada por `created_at`, así que un producto puede faltar en `read_all`. Que falte **no** demuestra que se haya borrado: antes de borrar se confirma con `GetProduct`. Si un producto queda fuera de una ejecución, su documento sigue en el índice y se actualiza en la siguiente. |
| Distancia en SQL | Operador `<=>` de pgvector vía `.op("<=>", return_type=Float)` | Tipado para mypy strict sin silenciar nada. `cosine_distance` no es visible para mypy sobre `Mapped[list[float]]`. |
| Lectura de filas | `result.all()` en lugar de `result.tuples()` | `Result.tuples()` está deprecado en SQLAlchemy 2.1 (salía un `SADeprecationWarning`). Además, `dict(result)` falla porque `Result` tiene `keys()`. |
| Carga del modelo | Perezosa y protegida con un lock, ejecutada en hilo con `asyncio.to_thread` | ONNX es trabajo de CPU y no debe bloquear el event loop. Si nada cambia, el reindexado ni siquiera carga el modelo. |
| CLI | `asynccontextmanager(get_session)` + los proveedores de `ui/dependencies.py` | Misma transacción (commit/rollback) y mismo cableado que la API, sin una configuración paralela. |
| `usage` | Pasa a ser nullable | En el fallback no hay ninguna llamada al LLM que reportar. |
| Router | Se quita el 503 de `responses` | El fallback sustituye al 503. Los errores de configuración siguen siendo 500. |
| BD de desarrollo | Al pasar de `postgres:16-alpine` a `pgvector/pgvector:pg16` se ejecutó `REINDEX TABLE products` | Es la misma versión mayor (datos compatibles), pero cambia la libc (musl → glibc) y la ordenación de texto podría diferir. El `REINDEX` reconstruye índices sin tocar datos. Se conservaron los 3 productos. |

## Correcciones tras la code review

La revisión (`/code-review medium`) dio 10 hallazgos. Se comprobó cada uno contra el código: 6 se
corrigen aquí (R1–R6), 2 repiten decisiones ya documentadas y 2 son falsos positivos (detalle al
final de esta sección). El usuario eligió corregir los 6 y añadió R7. Todos empiezan por un test
que falla con el código anterior.

| # | Qué | Por qué | Criterio de aceptación |
|---|---|---|---|
| R1 | Antes de borrar un documento «huérfano», confirmar con `catalog` (`GetProduct`, por su capa de aplicación) que el producto ya no existe | La paginación por `offset` sobre un `created_at` no único puede saltarse un producto en el borde de una página, y `IndexCatalog` lo borraba del índice aunque el producto siga existiendo | Un producto existente que `read_all` no devuelve **no** se borra. Uno que no existe sí. |
| R2 | El `content_hash` incluye el nombre del modelo de embeddings | Cambiar `EMBEDDING_MODEL` no recalculaba nada y dejaba vectores de dos modelos mezclados | Si cambia el modelo, el siguiente reindex vuelve a calcular todos los embeddings. |
| R3 | Calcular embeddings y hacer upsert en lotes de tamaño fijo | Un único `INSERT` con más de ~13.000 productos supera el límite de 65.535 parámetros de Postgres, y todo el reindex hacía rollback | Con un lote de 2 y 5 productos: llamadas de 2, 2 y 1. |
| R4 | `RAG_TOP_K` limitado a 40 | Con `hnsw.ef_search=40` (el valor por defecto), un k mayor devuelve ~40 resultados sin avisar | `rag_top_k=41` es un error de configuración. |
| R5 | La búsqueda abre y cierra su propia sesión | La sesión de la petición mantenía una conexión del pool durante toda la llamada al LLM (hasta 30 s). Con unas 15 preguntas concurrentes el pool se agota y bloquea `catalog` | Durante la llamada al LLM no queda ninguna conexión ocupada. |
| R6 | Cargar el modelo de embeddings al arrancar la app (lifespan) | La primera pregunta tras cada arranque cargaba el modelo y bloqueaba también a las concurrentes | Al arrancar la app se ejecuta un embedding de calentamiento. En tests se puede desactivar para no descargar el modelo. |
| R7 | Descargar el modelo **al construir la imagen** (Dockerfile) y, en ejecución, solo cargarlo de disco (`local_files_only=True`). Petición del usuario. | Si el modelo no viene en la imagen, cada contenedor nuevo lo descarga al arrancar: es más lento y depende de la red (y de un volumen de caché) | La imagen contiene el modelo. Un contenedor **sin red** (`--network none`) calcula embeddings. Con `local_files_only` y la caché vacía, falla en vez de descargar. Ya no hace falta el volumen `fastembed-cache`. |

**No aplicados, con su porqué:**

- **Acoplamiento `assistant` → `catalog`.** Repite el diseño documentado: solo la capa de
  aplicación de `catalog`, sus DTOs y su cableado.
- **Docstrings «narrativos» en los puertos.** Falso positivo: el `CLAUDE.md` del repo los permite
  en los puertos.
- **503 sin documentar.** Falso positivo: en esta ruta nada lanza un `ServiceUnavailableError`
  distinto de `LLMUnavailableError`, y el fallback lo captura.
- **500 si fallan los embeddings o la búsqueda.** Coherente con la especificación: el fallback
  cubre la caída del LLM. Sin recuperación no hay nada que devolver.

### Evidencia de las correcciones

**Rojo** (código anterior). Los 4 primeros fallan por el bug; el resto, porque la API que
necesitan aún no existe:

```
R1  test_r1_keeps_a_product_that_exists_but_was_not_listed      → deleted=1 (borraba un producto existente)
R2  test_r2_changing_the_embedding_model_reembeds_everything    → indexed=0 (no recalculaba nada)
R4  test_r4_rejects_more_than_the_hnsw_default_ef_search        → DID NOT RAISE ValidationError
R5  test_r5_no_connection_is_held_while_the_llm_answers         → assert [1] == [0] (1 conexión ocupada durante el LLM)
R1  test_r1_reports_only_ids_not_in_the_catalog (integración)   → falta CatalogReader.missing
R2  test_r2_same_content_with_another_model_has_another_hash    → falta el parámetro embedding_model
R3  test_r3_embeds_and_upserts_in_batches                       → falta el parámetro batch_size
R6  tests/e2e/test_lifespan.py                                  → ImportError: no existe contexts.assistant.ui.lifespan
R7  test_r7_fails_instead_of_downloading_when_the_model_is_not_cached → falta el parámetro local_files_only
```

**Verde** (tras las correcciones): esos 9 tests y 3 de control (R1 «sigue borrando lo que ya no
existe», R4 «acepta 40», R6 «sin calentamiento por defecto»): `12 passed`.

**R7 y R6 en ejecución real:**

- La imagen contiene el modelo: `/opt/fastembed` ocupa 241 MB y se ha construido con
  `EMBEDDING_LOCAL_FILES_ONLY=true`.
- La descarga es una capa propia del `Dockerfile`, **antes** de copiar el código, así que cambiar
  código no vuelve a descargarlo.
- Contenedor con `--network none`: `embed(["¿Cuánto cuesta el widget?"])` devuelve un vector de
  dimensión 384.
- Contenedor con `--network none`: `uvicorn main:app` llega a «Application startup complete» tras
  cargar el modelo en el lifespan.
- Con `local_files_only` y la caché vacía, fastembed lanza `ValueError: Could not load model …
  from any source` sin descargar nada (comprobado sin red y cubierto por el test R7).
- Ya no existe el volumen `fastembed-cache` en `docker-compose.yml`.

**Consecuencia de R2 en un índice ya existente:** el formato del hash cambia, así que el primer
`make reindex` tras desplegar recalcula todo una vez. En desarrollo: `indexed=3 unchanged=0
deleted=0` y después `indexed=0 unchanged=3 deleted=0`.

## Evidencia

| # | Resultado | Evidencia |
|---|---|---|
| C1 | ✅ | `make reindex` sobre la BD de desarrollo (3 productos), primera ejecución: `indexed=3 unchanged=0 deleted=0` (1 min 23 s, incluida la descarga del modelo). `product_documents`: 3 filas, 3 hashes distintos. Test `test_c1_indexes_every_product_into_an_empty_index`. |
| C2 | ✅ | Segunda ejecución: `indexed=0 unchanged=3 deleted=0` (2,9 s; el modelo no llega a cargarse). Test `test_c2_second_run_without_changes_embeds_nothing`: el `FakeEmbeddingClient` no recibe llamadas. |
| C3 | ✅ | Test `test_c3_only_the_changed_product_is_embedded_again`: solo se recalcula el embedding del producto renombrado. No se modificaron datos reales para probarlo. |
| C4 | ✅ | Test unitario `test_c4_deletes_documents_of_products_no_longer_in_the_catalog`. Integración contra pgvector: `test_c4_delete_removes_only_the_given_documents`. |
| C5 | ✅ | `git diff origin/main -- src/contexts/catalog` vacío. |
| C6 | ✅ | `grep contexts.catalog src/contexts/assistant` solo aparece en `infrastructure/catalog/list_products_catalog_reader.py` (capa de aplicación de `catalog`), `ui/dependencies.py` y `ui/cli/reindex.py` (cableado). `catalog` no importa `assistant`. |
| C7 | ✅ | Unitarios `test_c7_returns_retrieved_documents_as_sources` y `test_c7_puts_the_documents_and_the_question_in_the_prompt`. E2E `test_c7_returns_200_with_answer_sources_and_usage`. |
| C8 | ✅ | Unitarios `test_c8_llm_unavailable_*`. E2E `test_c8_returns_200_with_fallback_when_llm_unavailable`: 200, `fallback_used=true`, `usage=null`. |
| C9 | ✅ | E2E `test_c9_assistant_exposes_no_indexing_endpoint`: las rutas `/assistant*` de OpenAPI son exactamente `["/assistant/ask"]`. |
| C10 | ✅ | Integración `test_c10_returns_the_nearest_document_first`, contra pgvector real: orden `near`, `middle`, `far`, con similitud ≈ 0,995 para el primero. |
| C11 | ✅ local | `make lint`: ruff «All checks passed!», pylint 10.00/10, mypy «no issues found in 72 source files». `make test`: **137 passed** (antes 99), sin warnings. _CI: pendiente de la PR._ |
| C12 | ✅ | Plan actualizado, también con R1–R7. README: paso 2 del roadmap ✅, regla real sobre `catalog`, layout, stack, Quick Start (modelo en la imagen, `RAG_TOP_K` máximo 40) y testing al día, badge de 137 tests. Anclas y badges comprobados. |

### Recuperación real con el modelo multilingüe

Pregunta en español contra el índice de desarrollo, con los adaptadores reales (fastembed + pgvector):

```
¿Cuánto cuesta el widget?
0.361  SKU: PROD-LIVE-1 | Name: Real Widget | Price: 25.00 EUR
0.279  SKU: GATE-2 | Name: x | Price: 0.01 EUR
0.216  SKU: DUP-LIVE | Name: x | Price: 0.01 EUR
```

La pregunta, en español, recupera primero el producto cuyo nombre está en inglés.

### Tests nuevos o cambiados

| Fichero | Tests |
|---|---|
| `tests/unit/contexts/assistant/domain/test_product_document.py` | 5 (nuevo) |
| `tests/unit/contexts/assistant/application/test_index_catalog.py` | 5 (nuevo) |
| `tests/unit/contexts/assistant/application/test_ask_assistant.py` | 9 (antes 5) |
| `tests/unit/contexts/assistant/application/test_index_catalog.py` (R1–R3) | +4 |
| `tests/unit/shared/infrastructure/test_settings.py` (R4) | 2 (nuevo) |
| `tests/integration/contexts/assistant/application/test_ask_assistant_connection.py` (R5) | 1 (nuevo) |
| `tests/integration/contexts/assistant/infrastructure/test_fastembed_embedding_client.py` (R7) | 1 (nuevo) |
| `tests/e2e/test_lifespan.py` (R6) | 2 (nuevo) |
| `tests/integration/contexts/assistant/infrastructure/test_sqlalchemy_documents.py` | 7 (nuevo) |
| `tests/integration/contexts/assistant/infrastructure/test_list_products_catalog_reader.py` | 3 (nuevo) |
| `tests/e2e/test_assistant.py` | 7 (antes 5; el 503 pasa a fallback) |

### Fuera de lo verificado

- **Pregunta completa con el LLM real**: `.env` no tiene `ANTHROPIC_API_KEY`. La generación está cubierta por los tests con `FakeLLMClient` y por el adaptador probado en el PR 1. La recuperación real está demostrada arriba.
