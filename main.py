from fastapi import FastAPI

from contexts.catalog.ui.routers.products import router as products_router
from shared.infrastructure.exception_handlers import register_exception_handlers
from shared.infrastructure.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Reference FastAPI project: clean architecture (DDD + Hexagonal).",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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

    return application


app = create_app()
