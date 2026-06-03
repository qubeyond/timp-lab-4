import logging
from datetime import UTC, datetime

from fastapi import HTTPException

from src.domain.entities import DEFAULT_QUEUE, Queue, Room
from src.domain.repositories import (
    EventPublisher,
    QueueRepository,
    RoomRepository,
    TicketRepository,
)
from src.infrastructure.redis.queue_repo import generate_room_id
from src.services.auth import AuthService
from src.services.dto import NextCalled, QueueAdded, QueueRemoved, RoomClosed, RoomCreated

logger = logging.getLogger(__name__)


class RoomService:
    def __init__(
        self,
        queue_repo: QueueRepository,
        room_repo: RoomRepository,
        ticket_repo: TicketRepository,
        auth_service: AuthService,
        publisher: EventPublisher,
    ) -> None:
        self._qr = queue_repo
        self._rr = room_repo
        self._tr = ticket_repo
        self._auth = auth_service
        self._pub = publisher

    async def create_room(self, owner_id: str) -> RoomCreated:
        for _ in range(10):
            room_id = generate_room_id()

            if not await self._qr.room_exists(room_id):
                room = Room(room_id=room_id, owner_id=owner_id, queue_labels=[DEFAULT_QUEUE])
                await self._qr.set_owner(room_id, owner_id)
                await self._qr.save(Queue(label=DEFAULT_QUEUE, room_id=room_id))
                await self._rr.save(room)

                token = self._auth.create_token(owner_id, role="admin", room_id=room_id)
                logger.info("Room %s created by %s", room_id, owner_id)

                return RoomCreated(room_id=room_id, access_token=token)

        raise HTTPException(status_code=500, detail="Ошибка генерации ID комнаты")

    @staticmethod
    def _room_from(room_id: str, queues: list[Queue]) -> Room:
        # Источник истины правил — доменная сущность Room. Живое состояние
        # очередей лежит в Redis, поэтому собираем Room из актуальных меток
        # и делегируем ей решения (можно ли добавить/удалить, какая метка следующая).
        return Room(room_id=room_id, owner_id="", queue_labels=[q.label for q in queues])

    async def _assert_owner(self, room_id: str, user_id: str) -> None:
        # Двойная проверка владельца: роль admin уже проверена в токене, но
        # токен живёт дольше, чем комната в Redis (TTL), и 6-символьный ID
        # может быть переиспользован новой комнатой. Сверяемся с владельцем
        # в Redis, чтобы старый токен не управлял чужой комнатой.
        owner = await self._qr.get_owner(room_id)

        if owner is None or owner != user_id:
            raise HTTPException(status_code=403, detail="Доступ запрещён")

    async def close_room(self, room_id: str, user_id: str) -> RoomClosed:
        await self._assert_owner(room_id, user_id)

        await self._pub.publish(room_id, {"type": "update", "data": {"room_closed": True}})
        await self._qr.delete_all(room_id)
        await self._rr.close(room_id)

        logger.info("Room %s closed by %s", room_id, user_id)

        return RoomClosed(status="closed")

    async def add_queue(self, room_id: str, user_id: str) -> QueueAdded:
        await self._assert_owner(room_id, user_id)

        async with self._qr.lock(room_id):
            queues = await self._qr.load_all(room_id)
            room = self._room_from(room_id, queues)

            if not room.can_add_queue():
                raise HTTPException(status_code=400, detail="Достигнут максимум очередей")

            try:
                label = room.next_queue_label()
            except ValueError:
                raise HTTPException(status_code=400, detail="Достигнут максимум очередей") from None

            new_queue = Queue(label=label, room_id=room_id)
            longest = max(queues, key=lambda q: len(q.waiting), default=None)

            # Перебалансировка — доменная политика очереди: половина с хвоста
            # самой длинной переезжает в новую. При <2 ожидающих перенос пустой.
            if longest is not None:
                moved = longest.split_off_half()
                if moved:
                    new_queue.absorb(moved)
                    await self._qr.save(longest)

            await self._qr.save(new_queue)

        await self._pub.publish(room_id, {"type": "update"})

        return QueueAdded(queue_label=label)

    async def remove_queue(self, room_id: str, label: str, user_id: str) -> QueueRemoved:
        await self._assert_owner(room_id, user_id)

        async with self._qr.lock(room_id):
            queues = await self._qr.load_all(room_id)
            room = self._room_from(room_id, queues)

            if not room.can_remove_queue(label):
                if label not in room.queue_labels:
                    raise HTTPException(status_code=404, detail="Очередь не найдена")
                raise HTTPException(status_code=400, detail="Нельзя удалить единственную очередь")

            target = next(q for q in queues if q.label == label)
            remaining = [q for q in queues if q.label != label]

            # Перераспределяем ожидающих удаляемой очереди в самые короткие из оставшихся.
            for ticket in target.waiting:
                shortest = min(remaining, key=lambda q: len(q.waiting))
                shortest.absorb([ticket])

            for q in remaining:
                await self._qr.save(q)

            await self._qr.delete(room_id, label)

        await self._pub.publish(room_id, {"type": "update"})

        return QueueRemoved(queue_label=label)

    async def call_next(self, room_id: str, label: str, user_id: str) -> NextCalled:
        await self._assert_owner(room_id, user_id)

        async with self._qr.lock(room_id):
            queue = await self._qr.load(room_id, label)

            if queue is None:
                raise HTTPException(status_code=404, detail="Очередь не найдена")

            try:
                ticket = queue.call_next(datetime.now(UTC))
            except ValueError:
                raise HTTPException(status_code=400, detail="Очередь пуста") from None

            await self._qr.save(queue)

        await self._tr.mark_called(room_id, label, ticket.num, datetime.now(UTC))
        await self._pub.publish(room_id, {"type": "update"})

        logger.info("Ticket %s (queue %s) called in room %s", ticket.num, label, room_id)

        return NextCalled(queue_label=label, ticket=ticket.num)

    async def complete_serving(self, room_id: str, label: str, user_id: str) -> None:
        await self._assert_owner(room_id, user_id)

        async with self._qr.lock(room_id):
            queue = await self._qr.load(room_id, label)

            if queue is None:
                raise HTTPException(status_code=404, detail="Очередь не найдена")

            serving_since = queue.serving_since

            try:
                ticket = queue.complete_serving()
            except ValueError:
                raise HTTPException(status_code=400, detail="Обслуживание не активно") from None

            now = datetime.now(UTC)
            await self._qr.save(queue)

        await self._tr.mark_completed(room_id, label, ticket.num, now)

        if serving_since is not None:
            serve_seconds = int((now - serving_since).total_seconds())
            await self._qr.update_avg_serve(room_id, max(serve_seconds, 0))

        await self._pub.publish(room_id, {"type": "update"})

    async def get_stats(self, room_id: str) -> dict:
        history = await self._tr.load_history(room_id)
        completed = [r for r in history if r.completed_at]
        serve_times = [r.serve_seconds for r in completed if r.serve_seconds is not None]

        return {
            "room_id": room_id,
            "total_tickets": len(history),
            "completed": len(completed),
            "avg_serve_seconds": int(sum(serve_times) / len(serve_times)) if serve_times else 0,
            "timeline": history,
        }

    async def get_state(self, room_id: str, user_id: str) -> dict:
        if not await self._qr.room_exists(room_id):
            return {"room_closed": True, "room_id": room_id}

        queues = await self._qr.load_all(room_id)

        if not queues:
            return {"room_closed": True, "room_id": room_id}

        avg_serve = await self._qr.get_avg_serve(room_id)
        now = datetime.now(UTC)

        my_ticket, my_queue, my_pos = "--", "", "Нет в очереди"
        my_status, my_elapsed = "waiting", 0
        global_elapsed = 0
        queue_infos = []

        for queue in queues:
            label_elapsed = 0
            if queue.serving and queue.serving_since:
                label_elapsed = int((now - queue.serving_since).total_seconds())
                global_elapsed = max(global_elapsed, label_elapsed)

            current_ticket = queue.serving.num if queue.serving else ""
            queue_infos.append(
                {
                    "label": queue.label,
                    "length": len(queue.waiting),
                    "status": "serving" if queue.serving else "waiting",
                    "current_ticket": f"№ {current_ticket}" if current_ticket else "ОЖИДАНИЕ",
                    "elapsed_time": label_elapsed,
                }
            )

            if queue.serving and queue.serving.user_id == user_id:
                my_ticket = f"№ {queue.serving.num}"
                my_queue = queue.label
                my_pos = "На приеме"
                my_status = "serving"
                my_elapsed = label_elapsed
            else:
                pos = queue.position(user_id)
                if pos is not None:
                    ticket = queue.find_ticket(user_id)
                    my_ticket = f"№ {ticket.num}" if ticket else "--"
                    my_queue = queue.label
                    offset = 1 if queue.serving else 0
                    my_pos = str(pos + offset)
                    my_status = "waiting"

        return {
            "room_closed": False,
            "room_id": room_id,
            "current_status": my_status,
            "elapsed_time": my_elapsed,
            "avg_serve_seconds": avg_serve,
            "client_context": {
                "ticket_label": my_ticket,
                "queue_label": my_queue,
                "position_label": my_pos,
                "should_redirect": my_pos == "Нет в очереди",
            },
            "admin_context": {
                "queues": queue_infos,
                "elapsed_time": global_elapsed,
            },
        }
