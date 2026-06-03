from pydantic import BaseModel, Field


class RoomCreateRequest(BaseModel):
    is_open: bool = True
    balancer_enabled: bool = True


class RoomCreateResponse(BaseModel):
    room_id: str
    access_token: str
    token_type: str = Field(default="bearer")


class RoomCloseResponse(BaseModel):
    status: str


class WaitingTicket(BaseModel):
    ticket: str
    status: str
    position: int = Field(ge=1)


class QueueInfo(BaseModel):
    label: str
    code: str = ""
    length: int = Field(ge=0)
    status: str
    current_ticket: str
    current_status: str = ""
    elapsed_time: int = Field(default=0, ge=0)
    waiting: list[WaitingTicket] = Field(default_factory=list)


class ClientContext(BaseModel):
    ticket_label: str
    queue_label: str
    position_label: str
    ticket_status: str = ""
    should_redirect: bool


class AdminContext(BaseModel):
    queues: list[QueueInfo]
    elapsed_time: int = Field(default=0, ge=0)


class RoomStateResponse(BaseModel):
    room_closed: bool
    room_id: str
    is_open: bool = True
    balancer_enabled: bool = True
    is_owner: bool = False
    current_status: str | None = None
    elapsed_time: int | None = None
    avg_serve_seconds: int | None = None
    client_context: ClientContext | None = None
    admin_context: AdminContext | None = None
