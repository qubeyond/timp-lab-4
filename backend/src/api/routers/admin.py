from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import require_admin
from src.api.schemas.admin import (
    AddQueueRequest,
    CallNextResponse,
    CompleteServingResponse,
    QueueAction,
    QueueMutationResponse,
    RemoveQueueRequest,
    RoomStatsResponse,
    TicketTimeline,
)
from src.services.room import RoomService

router = APIRouter(prefix="/admin", tags=["admin"])


def _check_room(room_id: str, user: dict) -> None:
    if user.get("room_id") != room_id:
        raise HTTPException(status_code=403, detail="Нет доступа к этой комнате")


@router.post("/next", response_model=CallNextResponse)
@inject
async def call_next(
    payload: QueueAction,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.call_next(payload.room_id.upper(), payload.queue_label, user["sub"])

    return CallNextResponse(queue_label=result.queue_label, ticket=result.ticket)


@router.post("/complete", response_model=CompleteServingResponse)
@inject
async def complete_serving(
    payload: QueueAction,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    await room_service.complete_serving(payload.room_id.upper(), payload.queue_label, user["sub"])

    return CompleteServingResponse()


@router.post("/queue/add", response_model=QueueMutationResponse)
@inject
async def add_queue(
    payload: AddQueueRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.add_queue(payload.room_id.upper(), user["sub"])

    return QueueMutationResponse(status="created", queue_label=result.queue_label)


@router.delete("/queue/remove", response_model=QueueMutationResponse)
@inject
async def remove_queue(
    payload: RemoveQueueRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.remove_queue(
        payload.room_id.upper(), payload.queue_label, user["sub"]
    )

    return QueueMutationResponse(status="removed", queue_label=result.queue_label)


@router.get("/stats/{room_id}", response_model=RoomStatsResponse)
@inject
async def room_stats(
    room_id: str,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(room_id.upper(), user)

    result = await room_service.get_stats(room_id.upper())

    return RoomStatsResponse(
        room_id=result["room_id"],
        total_tickets=result["total_tickets"],
        completed=result["completed"],
        avg_serve_seconds=result["avg_serve_seconds"],
        timeline=[
            TicketTimeline(
                ticket=t.num,
                queue_label=t.queue_label,
                joined_at=t.joined_at,
                wait_seconds=t.wait_seconds,
                serve_seconds=t.serve_seconds,
            )
            for t in result["timeline"]
        ],
    )
