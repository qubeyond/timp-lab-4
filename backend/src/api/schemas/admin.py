from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.common import QueueLabel, RoomId


class QueueAction(BaseModel):
    room_id: RoomId
    queue_label: QueueLabel = Field(default="A")


class AddQueueRequest(BaseModel):
    room_id: RoomId


class RemoveQueueRequest(BaseModel):
    room_id: RoomId
    queue_label: QueueLabel


class EntryToggleRequest(BaseModel):
    room_id: RoomId
    is_open: bool


class BalancerToggleRequest(BaseModel):
    room_id: RoomId
    enabled: bool


class MoveTicketRequest(BaseModel):
    room_id: RoomId
    ticket: str = Field(min_length=1, max_length=16)
    to_queue: QueueLabel
    to_index: int = Field(ge=0)


class CallNextResponse(BaseModel):
    status: str = Field(default="called")
    queue_label: str
    ticket: str


class CompleteServingResponse(BaseModel):
    status: str = Field(default="completed")


class SkipResponse(BaseModel):
    status: str = Field(default="skipped")


class QueueMutationResponse(BaseModel):
    status: str
    queue_label: str
    code: str = ""


class RoomFlagResponse(BaseModel):
    is_open: bool | None = None
    balancer_enabled: bool | None = None


class InviteRequest(BaseModel):
    room_id: RoomId
    role: str = Field(default="full", pattern=r"^(full|queues)$")


class InviteResponse(BaseModel):
    token: str
    role: str


class CoAdminItem(BaseModel):
    user_id: str
    role: str


class CoAdminsResponse(BaseModel):
    admins: list[CoAdminItem]
    active_invites: int = Field(ge=0)


class RevokeAdminRequest(BaseModel):
    room_id: RoomId
    user_id: str = Field(min_length=1, max_length=64)


class RevokeAdminResponse(BaseModel):
    status: str = Field(default="revoked")


class AcceptInviteRequest(BaseModel):
    room_id: RoomId
    token: str = Field(min_length=8, max_length=128)


class AcceptInviteResponse(BaseModel):
    room_id: str
    access_token: str
    token_type: str = Field(default="bearer")


class LeaveAdminRequest(BaseModel):
    room_id: RoomId


class LeaveAdminResponse(BaseModel):
    status: str = Field(default="left")


class ResumeAdminRequest(BaseModel):
    room_id: RoomId


class ResumeAdminResponse(BaseModel):
    room_id: str
    access_token: str
    is_owner: bool
    token_type: str = Field(default="bearer")


class TicketTimeline(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket: str
    queue_label: str
    joined_at: datetime
    wait_seconds: int | None = None
    serve_seconds: int | None = None


class RoomStatsResponse(BaseModel):
    room_id: str
    total_tickets: int = Field(ge=0)
    completed: int = Field(ge=0)
    avg_serve_seconds: int = Field(ge=0)
    timeline: list[TicketTimeline]
