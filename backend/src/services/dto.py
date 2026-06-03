from dataclasses import dataclass


@dataclass
class RoomCreated:
    room_id: str
    access_token: str


@dataclass
class RoomClosed:
    status: str


@dataclass
class QueueAdded:
    queue_label: str
    code: str = ""


@dataclass
class QueueRemoved:
    queue_label: str


@dataclass
class NextCalled:
    queue_label: str
    ticket: str


@dataclass
class TicketTaken:
    is_admin: bool
    room_id: str | None = None
    queue_label: str | None = None
    access_token: str | None = None
    ticket: str | None = None
    position: int | None = None


@dataclass
class QueueLeft:
    status: str
