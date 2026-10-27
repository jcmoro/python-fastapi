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
3. El LLM del agente va por `langchain-anthropic`. Sus errores se traducen a `LLMUnavailableError`
   con la clasificación del PR 1, y se aplica el mismo timeout.
4. `assistant_mode` (`rag` | `agent`), con `rag` por defecto.
5. Evals con el marker `eval`, fuera del CI.

## Decisiones tomadas (con el usuario)

| Tema | Decisión |
|---|---|
| Límite de pasos | 5 llamadas a herramientas. Al llegar, respuesta en modo RAG y razón `max_steps` en el log. |
| `assistant_mode` | `rag` por defecto; los e2e del PR 2 no cambian. |
| Sin recomendación | «No hay una recomendación clara» y el top-k con nombre, SKU y precio, sin pregunta de seguimiento. |
| LLM del agente | Errores de `langchain-anthropic` traducidos con la misma clasificación que el PR 1, con el mismo timeout. |
| Clave para las evals | El usuario pone `ANTHROPIC_API_KEY` en `.env`. **Su valor nunca aparece en logs, salidas de comandos ni documentos.** |
| Primera ejecución real de evals | **Antes de lanzarla se informa al usuario del número de llamadas y del modelo** que usará. |
| Cliente de Anthropic | Los proveedores de `RecommendCandidate` y de `ClaudeCandidateAssessor` se crean aquí y reutilizan el único cliente de Anthropic del asistente, que se cierra en el lifespan (decidido en la code review del 3a). |

## Criterios de aceptación

| # | Criterio | Cómo se demuestra |
|---|---|---|
| B1 | Sin recomendación, la respuesta dice que no hay una clara y lista el top-k con nombre, SKU y precio | Test del agente |
| B2 | Al llegar a la 5.ª llamada a herramienta se corta, responde en modo RAG y el log registra `max_steps` | Test del grafo con un modelo falso guionizado |
| B3 | `assistant_mode=rag` es el valor por defecto, y los e2e del PR 2 pasan **sin modificarse** | `git diff` vacío en esos tests y suite en verde |
| B4 | Los errores del LLM del agente se clasifican como en el PR 1: los transitorios llevan al fallback y los de configuración se propagan | Test del adaptador del agente con errores simulados |
| B5 | El dominio y la aplicación de `assistant` no importan `langgraph` ni `langchain` | `grep` |
| B6 | Las evals existen con el marker `eval` y el CI por defecto no las ejecuta | Recolección de pytest y CI de la PR |
| B7 | Antes de la primera ejecución real se informa del número de llamadas, y el valor de la clave no aparece en ninguna salida | Mensaje al usuario antes de ejecutar, y revisión de las salidas |
| B8 | Los quality gates y el CI pasan | `make lint`, `make test` y CI de la PR |
| B9 | El plan y el README coinciden con el código | Revisión, anclas y badges |

## Evidencia

_Se completa al terminar._
