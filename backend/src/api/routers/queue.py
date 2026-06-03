from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, Request

from src.api.deps import get_current_user
from src.api.limiter import limiter
from src.api.schemas.queue import (
    JoinRequest,
    LeaveQueueResponse,
    StatusRequest,
    TakeTicketResponse,
)
from src.services.visitor import VisitorService

router = APIRouter(prefix="/queue", tags=["queue"])


@router.post("/ticket", response_model=TakeTicketResponse)
@limiter.limit("30/minute")
@inject
async def take_ticket(
    request: Request,
    payload: JoinRequest,
    user: Annotated[dict, Depends(get_current_user)],
    visitor_service: FromDishka[VisitorService],
):
    result = await visitor_service.take_ticket(
        payload.room_id.upper(),
        payload.queue_label,
        user["sub"],
        queue_code=payload.queue_code,
    )

    return TakeTicketResponse(
        is_admin=result.is_admin,
        room_id=result.room_id,
        queue_label=result.queue_label,
        access_token=result.access_token,
        ticket=result.ticket,
        position=result.position,
    )


@router.post("/leave", response_model=LeaveQueueResponse)
@limiter.limit("30/minute")
@inject
async def leave_queue(
    request: Request,
    payload: JoinRequest,
    user: Annotated[dict, Depends(get_current_user)],
    visitor_service: FromDishka[VisitorService],
):
    result = await visitor_service.leave_queue(payload.room_id.upper(), user["sub"])

    return LeaveQueueResponse(status=result.status)


@router.post("/status", response_model=LeaveQueueResponse)
@limiter.limit("30/minute")
@inject
async def set_status(
    request: Request,
    payload: StatusRequest,
    user: Annotated[dict, Depends(get_current_user)],
    visitor_service: FromDishka[VisitorService],
):
    result = await visitor_service.set_status(payload.room_id.upper(), user["sub"], payload.status)

    return LeaveQueueResponse(status=result.status)
