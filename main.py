from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from contexts.assistant.ui import lifespan as assistant_lifespan
from contexts.assistant.ui.routers.assistant import router as assistant_router
from contexts.catalog.ui.routers.products import router as products_router
from shared.infrastructure.exception_handlers import register_exception_handlers
from shared.infrastructure.settings import get_settings


def _lifespan(*, warm_up_models: bool) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        if warm_up_models:
            await assistant_lifespan.warm_up_embeddings()
        try:
            yield
        finally:
            await assistant_lifespan.close_anthropic_client()

    return lifespan


def create_app(*, warm_up_models: bool = False) -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Reference FastAPI project: clean architecture (DDD + Hexagonal).",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_lifespan(warm_up_models=warm_up_models),
    )

    @application.get(
        "/healthz",
        tags=["system"],
        summary="Liveness probe",
        description="Returns 200 if the process is up. No external dependencies are checked.",
    )
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    register_exception_handlers(application)
    application.include_router(products_router)
    application.include_router(assistant_router)

    return application


app = create_app(warm_up_models=True)
