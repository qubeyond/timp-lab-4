from pydantic import BaseModel, Field

from src.api.schemas.common import QueueLabel, RoomId


class JoinRequest(BaseModel):
    room_id: RoomId
    queue_label: QueueLabel | None = None
    queue_code: str | None = Field(default=None, min_length=1, max_length=8)


class TakeTicketResponse(BaseModel):
    is_admin: bool
    room_id: str | None = None
    queue_label: str | None = None
    access_token: str | None = None
    ticket: str | None = None
    position: int | None = Field(default=None, ge=1)


class StatusRequest(BaseModel):
    room_id: RoomId
    status: str = Field(pattern=r"^(waiting|on_way|no_show)$")


class LeaveQueueResponse(BaseModel):
    status: str
