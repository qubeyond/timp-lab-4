from datetime import UTC, datetime
from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.limiter import limiter
from src.api.schemas.auth import TokenResponse
from src.config import settings
from src.domain.enums import TokenType, UserRole
from src.domain.repositories import QueueRepository
from src.services.auth import REFRESH_COOKIE, AuthService, generate_identity

_bearer = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
@inject
async def get_token(
    request: Request,
    response: Response,
    auth_service: FromDishka[AuthService],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    fingerprint: str | None = None
    if refresh_token:
        try:
            payload = auth_service.decode_token(refresh_token)
            if payload.get("type") == TokenType.REFRESH:
                fingerprint = payload.get("sub")
        except HTTPException:
            fingerprint = None
    if not fingerprint:
        fingerprint = generate_identity()

    access_token = auth_service.create_token(fingerprint=fingerprint, role=UserRole.USER)
    auth_service.set_refresh_cookie(response, fingerprint)

    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
@inject
async def refresh_token(
    request: Request,
    response: Response,
    auth_service: FromDishka[AuthService],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh токен отсутствует")

    payload = auth_service.decode_token(refresh_token)

    if payload.get("type") != TokenType.REFRESH:
        raise HTTPException(status_code=401, detail="Невалидный тип токена")

    fingerprint: str = payload["sub"]
    access_token = auth_service.create_token(fingerprint=fingerprint, role=UserRole.USER)

    auth_service.set_refresh_cookie(response, fingerprint)

    return TokenResponse(access_token=access_token)


@router.post("/logout")
@inject
async def logout(
    request: Request,
    response: Response,
    auth_service: FromDishka[AuthService],
    queue_repo: FromDishka[QueueRepository],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
):
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")

    if credentials:
        try:
            payload = auth_service.decode_token(credentials.credentials)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                ttl = int(exp - datetime.now(UTC).timestamp())
                if ttl > 0:
                    await queue_repo.revoke_token(jti, ttl)
        except HTTPException:
            pass

    return {"status": "ok"}
