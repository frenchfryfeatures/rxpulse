import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import access, admin, auth, inventory, pharmacy
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.db.session import SessionLocal
from app.services.access import sync_catalogue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with SessionLocal() as db:
        await sync_catalogue(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RxPulse API",
        version="0.1.0",
        description="Eye care hospital inventory, pharmacy and RBAC API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    install_error_handlers(app)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "auth_mode": settings.auth_mode}

    for r in (auth.router, access.router, inventory.router, pharmacy.router, admin.router):
        app.include_router(r, prefix="/api/v1")
    if settings.auth_mode == "dev":
        app.include_router(auth.dev_router, prefix="/api/v1")
    return app


app = create_app()
