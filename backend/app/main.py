"""Cronos backend application entry point."""

from fastapi import FastAPI

from app.config import get_settings
from app.routers import auth, modules, users, work_item_types, work_items


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    @return The configured FastAPI instance.
    """
    settings = get_settings()
    app = FastAPI(title="cronos-api", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe endpoint.

        @return A JSON object reporting the service status.
        """
        return {"status": "ok"}

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(modules.router, prefix="/api/v1")
    app.include_router(work_items.router, prefix="/api/v1")
    app.include_router(work_item_types.router, prefix="/api/v1")

    return app


app = create_app()
