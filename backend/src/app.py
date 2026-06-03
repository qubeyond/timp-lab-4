import logging
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from src.api.limiter import limiter
from src.api.routers import admin, auth, feedback, health, queue, rooms, ws
from src.config import Settings, settings
from src.infrastructure.db.base import init_db
from src.ioc import create_container

logging.basicConfig(level=settings.log_level, format=settings.log_format)


def create_app() -> FastAPI:
    container = create_container()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = await container.get(AsyncEngine)
        await init_db(engine)
        yield
        await container.close()

    settings = Settings()

    app = FastAPI(
        title="Queue Service",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(_security_headers)

    setup_dishka(container, app)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(rooms.router, prefix="/api/v1")
    app.include_router(queue.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(feedback.router, prefix="/api/v1")
    app.include_router(ws.router)

    return app


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Слишком много запросов. Повторите через {exc.retry_after} сек."},
    )


async def _security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
