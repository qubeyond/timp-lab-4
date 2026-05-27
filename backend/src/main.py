import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from src.api.limiter import limiter
from src.api.routers import admin, auth, queue, rooms
from src.config import Settings
from src.domain.repositories import QueueRepo, WebSocketBroadcaster
from src.infrastructure.db.base import init_db
from src.infrastructure.ioc import create_container
from src.services.auth import AuthService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

container = create_container()


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Слишком много запросов. Повторите через {exc.retry_after} сек."},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = await container.get(AsyncEngine)
    await init_db(engine)
    yield
    await container.close()


_settings = Settings()

app = FastAPI(
    title="Queue Service",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _settings.debug else None,
    redoc_url="/redoc" if _settings.debug else None,
    openapi_url="/openapi.json" if _settings.debug else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)
setup_dishka(container, app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(rooms.router, prefix="/api/v1")
app.include_router(queue.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/")
async def healthcheck():
    return {"status": "ok"}


@app.get("/health")
async def health():
    import redis.asyncio as aioredis
    from sqlalchemy import text

    settings: Settings = await container.get(Settings)
    checks: dict[str, str] = {}

    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        eng = create_async_engine(settings.database_url)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await eng.dispose()
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"

    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", **checks},
    )


@app.websocket("/ws/room/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: Annotated[str | None, Query()] = None,
):
    room_id = room_id.upper().strip()

    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return

    settings: Settings = await container.get(Settings)
    auth_service = AuthService(settings)

    try:
        payload = auth_service.decode_token(token)
    except Exception:
        await websocket.close(code=4401, reason="Invalid token")
        return

    if payload.get("type") != "access":
        await websocket.close(code=4401, reason="Invalid token type")
        return

    u_id: str = payload.get("sub", "unknown")

    queue_repo: QueueRepo = await container.get(QueueRepo)
    broadcaster: WebSocketBroadcaster = await container.get(WebSocketBroadcaster)

    await broadcaster.connect(room_id, websocket, u_id)
    try:
        state = await queue_repo.get_state(room_id, u_id)
        await websocket.send_text(json.dumps({"type": "welcome", "data": state}))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        broadcaster.disconnect(room_id, websocket)
    except Exception as e:
        logging.getLogger(__name__).error("WS error: %s", e)
        broadcaster.disconnect(room_id, websocket)
