from dataclasses import dataclass, field
from datetime import datetime

from src.domain.constants import MAX_QUEUES, QUEUE_LABELS
from src.domain.enums import TicketStatus


@dataclass(frozen=True)
class TicketRecord:
    num: str
    queue_label: str
    joined_at: datetime
    called_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def wait_seconds(self) -> int | None:
        if self.called_at:
            return int((self.called_at - self.joined_at).total_seconds())
        return None

    @property
    def serve_seconds(self) -> int | None:
        if self.called_at and self.completed_at:
            return int((self.completed_at - self.called_at).total_seconds())
        return None


@dataclass
class Ticket:
    num: str
    user_id: str
    queue_label: str
    room_id: str
    status: str = TicketStatus.WAITING

    @staticmethod
    def build_num(label: str, count: int) -> str:
        return f"{label}{count + 1}"


@dataclass
class Queue:
    label: str
    room_id: str
    waiting: list[Ticket] = field(default_factory=list)
    serving: Ticket | None = None
    serving_since: datetime | None = None
    ticket_counter: int = 0

    code: str = ""

    def total_length(self) -> int:
        return len(self.waiting) + (1 if self.serving else 0)

    def set_status(self, user_id: str, status: str) -> Ticket | None:
        if self.serving is not None and self.serving.user_id == user_id:
            self.serving.status = status
            return self.serving
        ticket = next((t for t in self.waiting if t.user_id == user_id), None)
        if ticket is not None:
            ticket.status = status
        return ticket

    def move_ticket(self, user_id: str, to_index: int) -> bool:
        idx = next((i for i, t in enumerate(self.waiting) if t.user_id == user_id), None)
        if idx is None:
            return False
        ticket = self.waiting.pop(idx)
        to_index = max(0, min(to_index, len(self.waiting)))
        self.waiting.insert(to_index, ticket)
        return True

    def has_user(self, user_id: str) -> bool:
        in_waiting = any(t.user_id == user_id for t in self.waiting)
        in_serving = self.serving is not None and self.serving.user_id == user_id
        return in_waiting or in_serving

    def find_ticket(self, user_id: str) -> Ticket | None:
        if self.serving and self.serving.user_id == user_id:
            return self.serving
        return next((t for t in self.waiting if t.user_id == user_id), None)

    def position(self, user_id: str) -> int | None:
        for i, t in enumerate(self.waiting):
            if t.user_id == user_id:
                return i + 1
        return None

    def enqueue(self, user_id: str) -> Ticket:
        self.ticket_counter += 1
        ticket = Ticket(
            num=Ticket.build_num(self.label, self.ticket_counter - 1),
            user_id=user_id,
            queue_label=self.label,
            room_id=self.room_id,
        )
        self.waiting.append(ticket)
        return ticket

    def call_next(self, now: datetime) -> Ticket:
        if not self.waiting:
            raise ValueError("empty_queue")
        self.serving = self.waiting.pop(0)
        self.serving_since = now
        return self.serving

    def complete_serving(self) -> Ticket:
        if self.serving is None:
            raise ValueError("not_serving")
        done = self.serving
        self.serving = None
        self.serving_since = None
        return done

    def dequeue(self, user_id: str) -> Ticket | None:
        ticket = next((t for t in self.waiting if t.user_id == user_id), None)
        if ticket:
            self.waiting.remove(ticket)
        if self.serving and self.serving.user_id == user_id:
            ticket = self.serving
            self.serving = None
        return ticket

    def split_off_half(self) -> list[Ticket]:
        move_count = len(self.waiting) // 2
        if move_count == 0:
            return []
        moved = self.waiting[-move_count:]
        self.waiting = self.waiting[:-move_count]
        return moved

    def absorb(self, tickets: list[Ticket]) -> None:
        for t in tickets:
            t.queue_label = self.label
            self.waiting.append(t)
        self.ticket_counter += len(tickets)


@dataclass
class Room:
    room_id: str
    owner_id: str
    queue_labels: list[str] = field(default_factory=list)
    closed: bool = False

    is_open: bool = True

    balancer_enabled: bool = True

    def is_closed(self) -> bool:
        return self.closed

    def can_add_queue(self) -> bool:
        return len(self.queue_labels) < MAX_QUEUES

    def next_queue_label(self) -> str:
        available = [lbl for lbl in QUEUE_LABELS if lbl not in self.queue_labels]
        if not available:
            raise ValueError("max_queues")
        return available[0]

    def can_remove_queue(self, label: str) -> bool:
        return len(self.queue_labels) > 1 and label in self.queue_labels
