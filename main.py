from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from contexts.assistant.ui import lifespan as assistant_lifespan
from contexts.assistant.ui.routers.assistant import router as assistant_router
from contexts.catalog.ui.routers.products import router as products_router
from shared.infrastructure.exception_handlers import register_exception_handlers
from shared.infrastructure.settings import get_settings


@asynccontextmanager
async def _warm_up_models(_application: FastAPI) -> AsyncIterator[None]:
    await assistant_lifespan.warm_up_embeddings()
    yield


def create_app(*, warm_up_models: bool = False) -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Reference FastAPI project: clean architecture (DDD + Hexagonal).",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_warm_up_models if warm_up_models else None,
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
