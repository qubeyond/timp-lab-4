import logging
import secrets

from fastapi import HTTPException

from src.domain.enums import TicketStatus, UserRole, WsMessageType
from src.domain.repositories import EventPublisher, QueueRepository, TicketRepository
from src.services.auth import AuthService
from src.services.dto import QueueLeft, TicketTaken

logger = logging.getLogger(__name__)


class VisitorService:
    def __init__(
        self,
        queue_repo: QueueRepository,
        ticket_repo: TicketRepository,
        auth_service: AuthService,
        publisher: EventPublisher,
    ) -> None:
        self._qr = queue_repo
        self._tr = ticket_repo
        self._auth = auth_service
        self._pub = publisher

    async def take_ticket(
        self,
        room_id: str,
        queue_label_hint: str | None,
        user_id: str,
        queue_code: str | None = None,
    ) -> TicketTaken:
        if not await self._qr.room_exists(room_id):
            raise HTTPException(status_code=404, detail="Комната не существует")

        owner = await self._qr.get_owner(room_id)

        if owner == user_id:
            token = self._auth.create_token(user_id, role=UserRole.ADMIN, room_id=room_id)
            return TicketTaken(is_admin=True, room_id=room_id, access_token=token)

        flags = await self._qr.get_room_flags(room_id)

        if queue_code:
            label_by_code = await self._qr.find_label_by_code(room_id, queue_code)
            if label_by_code is None:
                raise HTTPException(status_code=404, detail="Неверный код очереди")
            queue_label_hint = label_by_code

        async with self._qr.lock(room_id):
            queues = await self._qr.load_all(room_id)

            for queue in queues:
                if queue.has_user(user_id):
                    ticket = queue.find_ticket(user_id)
                    pos = queue.position(user_id)

                    return TicketTaken(
                        is_admin=False,
                        queue_label=queue.label,
                        ticket=ticket.num if ticket else None,
                        position=pos,
                    )

            if not flags["is_open"]:
                raise HTTPException(status_code=403, detail="Приём заявок закрыт")

            if queue_label_hint:
                queue = next((q for q in queues if q.label == queue_label_hint), None)
                if queue is None:
                    raise HTTPException(status_code=404, detail="Очередь не существует")
            elif not flags["balancer_enabled"]:
                queue = secrets.choice(queues)
            else:
                queue = min(queues, key=lambda q: q.total_length())

            ticket = queue.enqueue(user_id)
            await self._qr.save(queue)
            position = queue.position(user_id)
            queue_label = queue.label

        await self._tr.save(ticket)
        await self._pub.publish(room_id, {"type": WsMessageType.UPDATE})

        logger.info("Ticket %s (queue %s) issued in room %s", ticket.num, queue_label, room_id)

        return TicketTaken(
            is_admin=False,
            queue_label=queue_label,
            ticket=ticket.num,
            position=position,
        )

    async def set_status(self, room_id: str, user_id: str, status: str) -> QueueLeft:
        """Посетитель сообщает статус (в пути / не приду) для своего талона."""
        if status not in set(TicketStatus):
            raise HTTPException(status_code=400, detail="Неизвестный статус")

        async with self._qr.lock(room_id):
            queues = await self._qr.load_all(room_id)
            for queue in queues:
                if queue.set_status(user_id, status) is not None:
                    await self._qr.save(queue)
                    break

        await self._pub.publish(room_id, {"type": WsMessageType.UPDATE})
        return QueueLeft(status=status)

    async def leave_queue(self, room_id: str, user_id: str) -> QueueLeft:
        async with self._qr.lock(room_id):
            queues = await self._qr.load_all(room_id)

            for queue in queues:
                if queue.has_user(user_id):
                    queue.dequeue(user_id)
                    await self._qr.save(queue)
                    break

        await self._pub.publish(room_id, {"type": WsMessageType.UPDATE})

        return QueueLeft(status="removed")
