from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, Request

from src.api.deps import get_current_user, require_admin
from src.api.limiter import limiter
from src.api.schemas.rooms import (
    RoomCloseResponse,
    RoomCreateRequest,
    RoomCreateResponse,
    RoomStateResponse,
)
from src.config import settings
from src.services.room import RoomService

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("", response_model=RoomCreateResponse)
@limiter.limit(settings.rate_limit_admin)
@inject
async def create_room(
    request: Request,
    user: Annotated[dict, Depends(get_current_user)],
    room_service: FromDishka[RoomService],
    payload: RoomCreateRequest | None = None,
):
    cfg = payload or RoomCreateRequest()
    result = await room_service.create_room(
        user["sub"], is_open=cfg.is_open, balancer_enabled=cfg.balancer_enabled
    )

    return RoomCreateResponse(room_id=result.room_id, access_token=result.access_token)


@router.delete("/{room_id}", response_model=RoomCloseResponse)
@limiter.limit(settings.rate_limit_admin)
@inject
async def close_room(
    request: Request,
    room_id: str,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    result = await room_service.close_room(room_id.upper(), user["sub"])

    return RoomCloseResponse(status=result.status)


@router.get("/{room_id}/state", response_model=RoomStateResponse)
@inject
async def room_state(
    room_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    room_service: FromDishka[RoomService],
):
    return await room_service.get_state(room_id.upper(), user["sub"])
