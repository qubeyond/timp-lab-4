from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.domain.enums import UserRole
from src.domain.repositories import QueueRepository
from src.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


@inject
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_service: FromDishka[AuthService],
    queue_repo: FromDishka[QueueRepository],
) -> dict:
    user = auth_service.verify_user(credentials)

    jti = user.get("jti")
    if jti and await queue_repo.is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Токен отозван")

    return user


async def require_admin(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    if user.get("role") != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Требуются права администратора")

    return user


async def require_room_admin(
    user: Annotated[dict, Depends(require_admin)],
) -> dict:
    return user
