from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import get_current_user, require_admin
from src.api.schemas.admin import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    AddQueueRequest,
    BalancerToggleRequest,
    CallNextResponse,
    CoAdminItem,
    CoAdminsResponse,
    CompleteServingResponse,
    EntryToggleRequest,
    InviteRequest,
    InviteResponse,
    LeaveAdminRequest,
    LeaveAdminResponse,
    MoveTicketRequest,
    QueueAction,
    QueueMutationResponse,
    RemoveQueueRequest,
    ResumeAdminRequest,
    ResumeAdminResponse,
    RevokeAdminRequest,
    RevokeAdminResponse,
    RoomFlagResponse,
    RoomStatsResponse,
    SkipResponse,
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


@router.post("/skip", response_model=SkipResponse)
@inject
async def skip_serving(
    payload: QueueAction,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    await room_service.skip_serving(payload.room_id.upper(), payload.queue_label, user["sub"])

    return SkipResponse()


@router.post("/move", response_model=QueueMutationResponse)
@inject
async def move_ticket(
    payload: MoveTicketRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    await room_service.move_ticket(
        payload.room_id.upper(),
        user["sub"],
        payload.ticket,
        payload.to_queue,
        payload.to_index,
    )

    return QueueMutationResponse(status="moved", queue_label=payload.to_queue)


@router.post("/entry", response_model=RoomFlagResponse)
@inject
async def toggle_entry(
    payload: EntryToggleRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.set_entry_open(
        payload.room_id.upper(), user["sub"], payload.is_open
    )

    return RoomFlagResponse(is_open=result["is_open"])


@router.post("/balancer", response_model=RoomFlagResponse)
@inject
async def toggle_balancer(
    payload: BalancerToggleRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.set_balancer(payload.room_id.upper(), user["sub"], payload.enabled)

    return RoomFlagResponse(balancer_enabled=result["balancer_enabled"])


@router.post("/invite", response_model=InviteResponse)
@inject
async def create_invite(
    payload: InviteRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.create_invite(payload.room_id.upper(), user["sub"], payload.role)

    return InviteResponse(token=result["token"], role=result["role"])


@router.get("/admins/{room_id}", response_model=CoAdminsResponse)
@inject
async def list_co_admins(
    room_id: str,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(room_id.upper(), user)

    result = await room_service.list_co_admins(room_id.upper(), user["sub"])

    return CoAdminsResponse(
        admins=[CoAdminItem(user_id=a["user_id"], role=a["role"]) for a in result["admins"]],
        active_invites=result["active_invites"],
    )


@router.post("/revoke-admin", response_model=RevokeAdminResponse)
@inject
async def revoke_co_admin(
    payload: RevokeAdminRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.revoke_co_admin(
        payload.room_id.upper(), user["sub"], payload.user_id
    )

    return RevokeAdminResponse(status=result["status"])


@router.post("/accept-invite", response_model=AcceptInviteResponse)
@inject
async def accept_invite(
    payload: AcceptInviteRequest,
    user: Annotated[dict, Depends(get_current_user)],
    room_service: FromDishka[RoomService],
):
    result = await room_service.accept_invite(payload.room_id.upper(), payload.token, user["sub"])

    return AcceptInviteResponse(room_id=result["room_id"], access_token=result["access_token"])


@router.post("/leave", response_model=LeaveAdminResponse)
@inject
async def leave_admin(
    payload: LeaveAdminRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.leave_admin(payload.room_id.upper(), user["sub"])

    return LeaveAdminResponse(status=result["status"])


@router.post("/resume", response_model=ResumeAdminResponse)
@inject
async def resume_admin(
    payload: ResumeAdminRequest,
    user: Annotated[dict, Depends(get_current_user)],
    room_service: FromDishka[RoomService],
):
    result = await room_service.resume_admin(payload.room_id.upper(), user["sub"])

    return ResumeAdminResponse(
        room_id=result["room_id"],
        access_token=result["access_token"],
        is_owner=result["is_owner"],
    )


@router.post("/queue/add", response_model=QueueMutationResponse)
@inject
async def add_queue(
    payload: AddQueueRequest,
    user: Annotated[dict, Depends(require_admin)],
    room_service: FromDishka[RoomService],
):
    _check_room(payload.room_id.upper(), user)

    result = await room_service.add_queue(payload.room_id.upper(), user["sub"])

    return QueueMutationResponse(status="created", queue_label=result.queue_label, code=result.code)


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
