import contextlib
import secrets
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

import redis.asyncio as aioredis

from src.domain.entities import DEFAULT_QUEUE, ROOM_ID_ALPHABET, ROOM_ID_LENGTH, Queue, Ticket
from src.infrastructure.redis.client import (
    queue_counter_key,
    queue_current_key,
    queue_hash_key,
    queue_list_key,
    room_avg_serve_key,
    room_lock_key,
    room_owner_key,
    room_queues_key,
    room_serve_count_key,
    user_queue_key,
)

# Параметры блокировки на комнату. timeout — авто-снятие, если держатель упал;
# blocking_timeout — сколько ждём очереди на лок, прежде чем сдаться.
_LOCK_TIMEOUT = 5.0
_LOCK_BLOCKING_TIMEOUT = 5.0


def generate_room_id() -> str:
    return "".join(secrets.choice(ROOM_ID_ALPHABET) for _ in range(ROOM_ID_LENGTH))


class RedisQueueRepository:
    def __init__(self, redis: aioredis.Redis, queue_ttl: int) -> None:
        self._r = redis
        self._ttl = queue_ttl

    def lock(self, room_id: str) -> AbstractAsyncContextManager[None]:
        # Нативный Redis-лок: сериализует мутации одной комнаты, чтобы
        # параллельные load→mutate→save не затирали друг друга
        # (двойной вызов талона, потеря людей при одновременном входе).
        return self._r.lock(
            room_lock_key(room_id),
            timeout=_LOCK_TIMEOUT,
            blocking=True,
            blocking_timeout=_LOCK_BLOCKING_TIMEOUT,
        )

    async def room_exists(self, room_id: str) -> bool:
        return bool(await self._r.exists(room_owner_key(room_id)))

    async def get_owner(self, room_id: str) -> str | None:
        return await self._r.get(room_owner_key(room_id))

    async def set_owner(self, room_id: str, user_id: str) -> None:
        await self._r.set(room_owner_key(room_id), user_id, ex=self._ttl)

    async def load(self, room_id: str, label: str) -> Queue | None:
        ck = queue_current_key(room_id, label)
        async with self._r.pipeline(transaction=False) as pipe:
            pipe.exists(ck)
            pipe.hgetall(ck)
            pipe.lrange(queue_list_key(room_id, label), 0, -1)
            pipe.get(queue_counter_key(room_id, label))
            exists, current, user_ids, counter = await pipe.execute()

        if not exists:
            return None

        waiting: list[Ticket] = []

        if user_ids:
            nums = await self._r.hmget(queue_hash_key(room_id, label), user_ids)
            for user_id, num in zip(user_ids, nums, strict=False):
                if num:
                    waiting.append(
                        Ticket(num=num, user_id=user_id, queue_label=label, room_id=room_id)
                    )

        serving: Ticket | None = None
        serving_since: datetime | None = None

        if current.get("status") == "serving" and current.get("ticket"):
            serving = Ticket(
                num=current["ticket"],
                user_id=current.get("active_user_id", ""),
                queue_label=label,
                room_id=room_id,
            )
            raw_ts = current.get("started_at", "")

            if raw_ts:
                with contextlib.suppress(ValueError):
                    serving_since = datetime.fromtimestamp(float(raw_ts), tz=UTC)

        return Queue(
            label=label,
            room_id=room_id,
            waiting=waiting,
            serving=serving,
            serving_since=serving_since,
            ticket_counter=int(counter) if counter else 0,
        )

    async def load_all(self, room_id: str) -> list[Queue]:
        labels = await self._r.lrange(room_queues_key(room_id), 0, -1)

        if not labels:
            return []

        queues = []

        for label in sorted(labels):
            q = await self.load(room_id, label)
            if q is not None:
                queues.append(q)

        return queues

    async def save(self, queue: Queue) -> None:
        lk = queue_list_key(queue.room_id, queue.label)
        hk = queue_hash_key(queue.room_id, queue.label)
        uqk = user_queue_key(queue.room_id)
        ck = queue_current_key(queue.room_id, queue.label)
        ck_val = queue_counter_key(queue.room_id, queue.label)

        serving = queue.serving

        # started_at — epoch-секунды начала обслуживания. Источник истины —
        # queue.serving_since. Если по какой-то причине его нет (объект собран
        # вручную без времени), сохраняем уже записанное значение, чтобы не
        # обнулить отсчёт у активного приёма. Без обслуживания — пустая строка.
        if serving and queue.serving_since is not None:
            started_at = str(queue.serving_since.timestamp())
        elif serving:
            started_at = (await self._r.hget(ck, "started_at")) or ""
        else:
            started_at = ""

        current_mapping = {
            "status": "serving" if serving else "waiting",
            "ticket": serving.num if serving else "",
            "active_user_id": serving.user_id if serving else "",
            "started_at": started_at,
        }

        async with self._r.pipeline(transaction=True) as pipe:
            pipe.delete(lk)
            pipe.delete(hk)

            for ticket in queue.waiting:
                pipe.rpush(lk, ticket.user_id)
                pipe.hset(hk, ticket.user_id, ticket.num)
                pipe.hset(uqk, ticket.user_id, queue.label)

            pipe.hset(ck, mapping=current_mapping)
            pipe.set(ck_val, queue.ticket_counter, ex=self._ttl)
            pipe.expire(lk, self._ttl)
            pipe.expire(hk, self._ttl)
            pipe.expire(uqk, self._ttl)
            pipe.expire(ck, self._ttl)

            await pipe.execute()

        labels = await self._r.lrange(room_queues_key(queue.room_id), 0, -1)

        if queue.label not in labels:
            await self._r.rpush(room_queues_key(queue.room_id), queue.label)
            await self._r.expire(room_queues_key(queue.room_id), self._ttl)

    async def delete(self, room_id: str, label: str) -> None:
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.delete(queue_list_key(room_id, label))
            pipe.delete(queue_hash_key(room_id, label))
            pipe.delete(queue_current_key(room_id, label))
            pipe.delete(queue_counter_key(room_id, label))
            pipe.lrem(room_queues_key(room_id), 0, label)
            await pipe.execute()

    async def delete_all(self, room_id: str) -> None:
        labels = await self._r.lrange(room_queues_key(room_id), 0, -1) or [DEFAULT_QUEUE]
        keys = [
            room_owner_key(room_id),
            room_queues_key(room_id),
            user_queue_key(room_id),
            room_avg_serve_key(room_id),
            room_serve_count_key(room_id),
        ]

        for label in labels:
            keys += [
                queue_list_key(room_id, label),
                queue_hash_key(room_id, label),
                queue_current_key(room_id, label),
                queue_counter_key(room_id, label),
            ]

        async with self._r.pipeline() as pipe:
            for k in keys:
                pipe.delete(k)
            await pipe.execute()

    async def get_avg_serve(self, room_id: str) -> int | None:
        val = await self._r.get(room_avg_serve_key(room_id))
        return int(val) if val else None

    # Атомарный пересчёт кумулятивного среднего на стороне Redis.
    # Без этого два одновременных complete_serving в одной комнате читают
    # одно и то же prev_avg/prev_cnt и затирают результат друг друга.
    _UPDATE_AVG_LUA = """
    local avg_key = KEYS[1]
    local cnt_key = KEYS[2]
    local serve = tonumber(ARGV[1])
    local ttl = tonumber(ARGV[2])
    local count = tonumber(redis.call('GET', cnt_key) or '0') + 1
    local prev_avg = redis.call('GET', avg_key)
    local new_avg
    if prev_avg == false then
        new_avg = serve
    else
        prev_avg = tonumber(prev_avg)
        new_avg = math.floor(prev_avg + (serve - prev_avg) / count)
    end
    redis.call('SET', avg_key, new_avg, 'EX', ttl)
    redis.call('SET', cnt_key, count, 'EX', ttl)
    return new_avg
    """

    async def update_avg_serve(self, room_id: str, serve_seconds: int) -> None:
        await self._r.eval(
            self._UPDATE_AVG_LUA,
            2,
            room_avg_serve_key(room_id),
            room_serve_count_key(room_id),
            serve_seconds,
            self._ttl,
        )
