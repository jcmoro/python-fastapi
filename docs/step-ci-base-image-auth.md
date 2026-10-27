# CI — Pull autenticado de imágenes desde Docker Hub

Rama `fix/ci-base-image`.

## Qué

- La imagen base del `Dockerfile` pasa de `public.ecr.aws/docker/library/python:3.12-slim` a
  `python:3.12-slim` (Docker Hub). Es la misma imagen oficial servida desde otro registro.
- Los dos jobs del CI (`lint` y `test`) hacen login en Docker Hub con `docker/login-action@v4`
  antes de construir la imagen.

## Por qué

En la PR #4 el job de lint falló dos veces seguidas al resolver la imagen base:

```
ERROR: failed to build: failed to solve: public.ecr.aws/docker/library/python:3.12-slim:
failed to resolve source metadata ... 429 Too Many Requests
toomanyrequests: Data limit exceeded
```

- ECR Public limita los pulls **no autenticados** a 500 GB de datos al mes, sin posibilidad de
  ampliarlo.
  [Amazon ECR Public service quotas](https://docs.aws.eu/AmazonECR/latest/public/public-service-quotas.html)
- Según fuentes secundarias, ese límite es por IP de origen.
  [KINTO Tech Blog](https://blog.kinto-technologies.com/posts/2025-04-28-migrate_from_dokcerhub_to_publicecr/)
  Los runners de GitHub comparten IPs, así que otros pueden haber agotado la cuota. Encaja con lo
  observado: el job de tests, en otro runner, sí pudo hacer el pull.
- La caché de GHA no evita la llamada: BuildKit resuelve el manifiesto en el registro aunque las
  capas estén cacheadas, y el fallo se produjo justo ahí.

La causa es el **pull anónimo desde IPs compartidas**. La solución es autenticar el pull, para que
el límite sea de una cuenta y no de la IP del runner.

## Decisiones y porqué

### 1. Docker Hub con login (opciones descartadas, con su porqué)

| Opción | Decisión |
|---|---|
| ECR Public autenticado vía OIDC | **Descartada**: requiere una cuenta de AWS y no la hay. Se llegó a preparar y se revirtió sin commit. |
| Docker Hub **sin** login | **Descartada**: 100 pulls cada 6 horas por IP ([Docker Docs](https://docs.docker.com/docker-hub/usage/pulls/)). Es el mismo problema de IPs compartidas. Que los runners de GitHub estén exentos solo lo afirma una [fuente secundaria](https://learnk8s.io/t/597e48a3-c8f7-4134-a85f-e79706555366?s=17); no está confirmado. |
| `mirror.gcr.io` | **Descartada**: no tiene cuota publicada; solo [blogs](https://devtron.ai/blog/dodging-docker-hub-rate-limits-the-ultimate-cheat-code-for-your-ci-cd-pipeline/) dicen que funciona. |
| Mirror propio en GHCR | **Descartada**: no necesita cuentas nuevas, pero añade un workflow de copia y Dependabot dejaría de proponer actualizaciones de la imagen base. |
| Construir una vez y compartir entre jobs | **Descartada**: reduce los pulls a la mitad pero no ataca la causa. |
| **Docker Hub con login (elegida)** | La cuenta Personal gratuita tiene un límite propio: 200 pulls cada 6 horas ([Docker Docs](https://docs.docker.com/docker-hub/usage/pulls/)). Es la opción con menos piezas. |

### 2. El login también cubre `postgres:16-alpine`

El job de tests descarga `postgres:16-alpine` de Docker Hub con `docker compose`. Como el login se
hace antes, ese pull también sale autenticado y deja de estar expuesto al límite anónimo.

### 3. Secrets duplicados: de Actions y de Dependabot

En las ejecuciones que lanza Dependabot, los secrets de Actions no están disponibles: el contexto
`secrets` se rellena con los **secrets de Dependabot**
([GitHub Docs](https://docs.github.com/pt/enterprise-cloud@latest/code-security/reference/supply-chain-security/troubleshoot-dependabot/dependabot-on-actions)).
Por eso `DOCKERHUB_USERNAME` y `DOCKERHUB_TOKEN` se crean con el mismo nombre en los dos
almacenes. Sin los de Dependabot, el CI de sus PRs fallaría en el login.

El usuario va en un secret y no en una variable (`vars`) porque no está documentado que `vars`
llegue a las ejecuciones de Dependabot.

### 4. Token de solo lectura

Se usa un Personal Access Token de Docker Hub con alcance **Public Repo Read-only**, no la
contraseña de la cuenta. Si se filtra, solo sirve para descargar imágenes públicas.

### 5. Sin línea comentada en el `Dockerfile`

El `Dockerfile` tenía `#FROM python:3.12-slim` comentado sobre el `FROM` de ECR. Se queda una sola
línea `FROM`, sin comentario, según la regla del repo contra comentarios narrativos.

### 6. Versión de la action

`docker/login-action@v4`. La última versión es v4.7.0, publicada el 2026-10-23. Se fija la versión
mayor, igual que el resto de actions del workflow; Dependabot la mantiene al día.

## Consecuencias conocidas

- **PRs desde forks:** no reciben secrets, así que el login fallará en su CI. El repo es personal
  y hoy no recibe PRs de forks.
- **Desarrollo local:** `make install` descarga `python:3.12-slim` de Docker Hub, sin login o con
  el login local de cada desarrollador. No cambia nada respecto a hoy.

## Configuración (manual, una vez)

1. Crear una cuenta gratuita en Docker Hub, si no existe.
2. Docker Hub → Account settings → Personal access tokens → New token, con alcance
   **Public Repo Read-only**.
3. Crear los cuatro secrets. La cuenta `gh` activa (`jcmorodiaz`) no tiene permisos en el repo,
   así que se usa el token de `jcmoro`. Cada comando pide el valor de forma interactiva, para que
   no quede en el historial:

   ```sh
   export GH_TOKEN="$(gh auth token --user jcmoro)"
   gh secret set DOCKERHUB_USERNAME --repo jcmoro/python-fastapi
   gh secret set DOCKERHUB_TOKEN    --repo jcmoro/python-fastapi
   gh secret set DOCKERHUB_USERNAME --repo jcmoro/python-fastapi --app dependabot
   gh secret set DOCKERHUB_TOKEN    --repo jcmoro/python-fastapi --app dependabot
   unset GH_TOKEN
   ```

## Incidencia al configurar los secrets

Los intentos 1 y 2 del CI de la PR #5 fallaron en el login, en ambos jobs:

```
Error response from daemon: Get "https://registry-1.docker.io/v2/":
unknown: malformed HTTP Authorization header
```

- **Diagnóstico:** las credenciales eran válidas. Un `docker login --password-stdin` local, con un
  `DOCKER_CONFIG` temporal para no tocar la configuración del usuario, devolvió
  `Login Succeeded`. El usuario y el token tampoco tenían comillas, espacios ni retornos de carro.
  El fallo estaba en los valores guardados en GitHub: se habían introducido con `read` y `!` desde
  Claude Code, donde no hay TTY, así que quedaron vacíos o mal.
- **Arreglo:** se volvieron a guardar leyendo el `.env` local (ignorado por git) y enviándolos por
  stdin con `printf '%s' ... | gh secret set`, en Actions y en Dependabot. El intento 3 pasó.
- **Lección:** `gh secret set` y `docker login` con `read` necesitan una terminal real. Desde `!`
  hay que pasar el valor por stdin desde un fichero o una variable, nunca con un prompt
  interactivo.

## Criterios de cierre

| Criterio | Evidencia |
|---|---|
| `actionlint` sin errores | Hecho: sin salida, exit 0. |
| La imagen se construye con la nueva base | Hecho: `docker build --pull` local correcto. |
| CI verde en la PR de este arreglo, con «Log in to Docker Hub» correcto en ambos jobs | Hecho: PR #5, run `40549577833`, intento 3. En los dos jobs pasan login, build, lint, migraciones y tests. |
| CI verde en una PR de **Dependabot** tras el merge (rebase de #1, #2 o #3) | Hecho, en las tres, todas con actor y disparador `dependabot[bot]`: #1 run `40554557052`, #2 run `40558395246`, #3 run `40554573505`. En todas pasan login, build, lint y tests, así que los secrets de Dependabot llegan a sus ejecuciones. Las tres están mergeadas. |
| Job de lint verde en la PR #4 | Hecho: run `40559156496` sobre `9258f58`, el commit con el que «Update branch» de GitHub mergeó `main` en la rama. Pasan lint y tests. |

## Notas de la verificación

- **#2 no respondió a `@dependabot rebase`**, aunque GitHub la daba como mergeable y sin
  conflictos. Con `@dependabot recreate` se regeneró sobre `main` y su CI pasó.
- **La PR #4 se actualizó con un merge, no con un rebase.** El permiso de esta sesión bloquea el
  push forzado (`Git Destructive`), así que se usó «Update branch» de GitHub, que hace el merge
  en el servidor. Se comprobó que el contenido de la PR respecto a `main` no cambió: los mismos 36
  ficheros, +1245/−6.

## Pendiente (fuera de alcance)

- `.github/dependabot.yml` pide las etiquetas `dependencies`, `python`, `github-actions` y
  `docker`, y ninguna existe en el repo (comprobado con `gh label list`). Dependabot lo avisó en
  la #2. Hay que crearlas o quitarlas de la configuración.
