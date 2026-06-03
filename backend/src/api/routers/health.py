import redis.asyncio as aioredis
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import Settings

router = APIRouter(tags=["health"])


@router.get("/")
async def healthcheck():
    return {"status": "ok"}


@router.get("/health")
@inject
async def health(settings: FromDishka[Settings]):
    checks: dict[str, str] = {}
    version = settings.app_version

    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    try:
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
        content={"status": "ok" if ok else "degraded", "version": version, **checks},
    )
