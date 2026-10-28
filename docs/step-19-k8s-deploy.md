# Paso 19 — Despliegue en Kubernetes (PR 4)

## Qué

Hay que desplegar en un clúster `kind` local la misma imagen que se usa en desarrollo y en CI:

- la API;
- Postgres con pgvector;
- un `Job` de migración (`alembic upgrade head`);
- un `Job` de reindexado (`python -m contexts.assistant.ui.cli.reindex`).

Para manejarlo hay cuatro objetivos de `make`: `make k8s-up`, `make k8s-deploy`, `make k8s-smoke` y
`make k8s-down`. Un workflow de CI aparte repite el despliegue y la prueba de humo.

## Por qué

Para demostrar que la imagen funciona tal cual fuera de Docker Compose:

- los secretos llegan por `Secret`;
- las migraciones y el reindexado son pasos explícitos;
- el modelo de embeddings ya va dentro de la imagen, así que los pods no descargan nada.

## Decisiones

| Decisión | Por qué |
|---|---|
| `kustomize` (`kubectl apply -k k8s`), sin Helm | Pocos recursos y ningún valor que parametrizar todavía |
| Los `Job` van en `k8s/jobs/`, fuera de la kustomization, y `make` los lanza en orden: BD lista → migrar → reindexar → API | Si se aplicaran a la vez que la BD, fallarían y dependerían de los reintentos. Con el orden explícito, cada paso empieza cuando el anterior ha terminado. |
| `make k8s-deploy` borra y vuelve a crear los `Job` | Un `Job` no se puede modificar. Así el objetivo se puede repetir sin efectos. |
| `rollout restart` de la API al final | `kind load` reemplaza `fastapi-api:latest`, pero sin reinicio el pod seguiría con la imagen anterior |
| Los secretos los crea `make`, y `k8s/secrets.example.yaml` es solo una plantilla que no se aplica | En el repositorio no hay ningún valor real |
| `ANTHROPIC_API_KEY` se pasa por stdin, filtrando solo esa línea de `.env` | La clave no aparece en ningún comando ni en la salida. Sin clave, el `Secret` queda vacío y es `optional`, así que `rag` responde con el fallback. |
| La API se arranca sin `--reload` (se sobrescribe el `command`) | El `CMD` del Dockerfile es el de desarrollo |
| Sondas: `startupProbe` para el calentamiento del modelo; `liveness` y `readiness` en `/healthz` | `/healthz` no comprueba dependencias, y así un fallo de la BD no reinicia el pod |
| `imagePullPolicy: IfNotPresent` | Con la etiqueta `:latest`, el valor por defecto sería `Always`, y fallaría con una imagen cargada por `kind` |
| El Dockerfile copia `alembic.ini` y `alembic/` | Antes solo los montaba Compose, y el `Job` de migración no podía ejecutarse desde la imagen |
| El CI va en un workflow aparte (`k8s.yml`), filtrado por rutas y también lanzable a mano | Es el «job opcional» del plan: no hace más lentos los PR que no tocan el despliegue |
| Sin AWS | El usuario no tiene cuenta. El paso opcional del plan queda fuera. |

## Criterios de aceptación

| # | Criterio | Evidencia |
|---|---|---|
| K1 | `make k8s-deploy` crea el clúster, carga la imagen, crea los secretos, espera a la BD, migra, reindexa y despliega la API | Ver «Evidencia» |
| K2 | La migración se ejecuta desde la imagen, sin volúmenes | Log del `Job` `migrate`: revisiones 1 → 4 |
| K3 | `make k8s-smoke` pasa a través del `Service` | `{"status":"ok"}` y `[]` |
| K4 | Repetir `make k8s-deploy` no tiene efectos y conserva los datos | La segunda ejecución sale con 0; la BD no se reinicia (generación 1, 0 reinicios) y `kubectl diff` sale vacío |
| K5 | El reindexado calcula los embeddings dentro del pod, sin red | Un producto creado antes del segundo despliegue → `indexed=1` |
| K6 | La clave no aparece en la salida | 0 apariciones de `sk-ant` en la salida del despliegue; el `Secret` solo contiene `ANTHROPIC_API_KEY` |
| K7 | El workflow `k8s` pasa en el PR | Enlace al run del PR |

## Evidencia (local, kind v0.33.0)

Primer `make k8s-deploy`: sale con 0.

```
job.batch/migrate condition met
job.batch/reindex condition met
deployment "api" successfully rolled out
```

```
pod/api-…     1/1   Running
pod/db-0      1/1   Running
job.batch/migrate   Complete   1/1   5s
job.batch/reindex   Complete   1/1   5s
```

Log del `Job` `migrate`: `init → products → product_documents → catalog columns`.
`reindex`: `indexed=0 unchanged=0 deleted=0`.

`make k8s-smoke`:

```
{"status":"ok"}
[]
```

Después de crear el producto `K8S-1` con `POST /products`, un segundo `make k8s-deploy` sale con 0 y
el `reindex` da `indexed=1 unchanged=0 deleted=0`. El `StatefulSet` `db` sigue en la generación 1,
`db-0` tiene 0 reinicios y `kubectl diff -k k8s` sale vacío. El `configured` de esa segunda
ejecución solo era la anotación de `kubectl apply`.
