import asyncio
import contextlib
import json
import time

import redis.asyncio as aioredis
from fastapi import WebSocket

from src.infrastructure.redis.client import (
    DEFAULT_QUEUE,
    queue_counter_key,
    queue_current_key,
    queue_hash_key,
    queue_list_key,
    room_avg_serve_key,
    room_owner_key,
    room_queues_key,
    room_serve_count_key,
    user_queue_key,
)


class RedisQueueRepo:
    def __init__(self, redis: aioredis.Redis, queue_ttl: int) -> None:
        self._r = redis
        self._ttl = queue_ttl

    async def room_exists(self, room_id: str) -> bool:
        labels = await self.get_queues(room_id)
        return bool(await self._r.exists(queue_current_key(room_id, labels[0])))

    async def get_owner(self, room_id: str) -> str | None:
        return await self._r.get(room_owner_key(room_id))

    async def set_owner(self, room_id: str, fingerprint: str) -> None:
        await self._r.set(room_owner_key(room_id), fingerprint, ex=self._ttl)

    async def get_queues(self, room_id: str) -> list[str]:
        labels = await self._r.lrange(room_queues_key(room_id), 0, -1)
        return sorted(labels) if labels else [DEFAULT_QUEUE]

    async def init_queue(self, room_id: str, label: str) -> None:
        ck = queue_current_key(room_id, label)
        await self._r.hset(
            ck,
            mapping={"status": "waiting", "ticket": "", "active_user_id": "", "started_at": ""},
        )
        async with self._r.pipeline() as pipe:
            pipe.expire(ck, self._ttl)
            pipe.expire(queue_list_key(room_id, label), self._ttl)
            pipe.expire(queue_hash_key(room_id, label), self._ttl)
            pipe.expire(queue_counter_key(room_id, label), self._ttl)
            pipe.expire(user_queue_key(room_id), self._ttl)
            pipe.rpush(room_queues_key(room_id), label)
            pipe.expire(room_queues_key(room_id), self._ttl)
            await pipe.execute()

    async def add_queue(self, room_id: str, label: str) -> bool:
        existing = await self.get_queues(room_id)
        if label in existing:
            return False
        await self.init_queue(room_id, label)

        lengths = {lbl: await self._r.llen(queue_list_key(room_id, lbl)) for lbl in existing}
        longest = max(lengths, key=lambda lbl: lengths[lbl])
        if lengths[longest] >= 1:
            src_list = queue_list_key(room_id, longest)
            src_hash = queue_hash_key(room_id, longest)
            dst_list = queue_list_key(room_id, label)
            dst_hash = queue_hash_key(room_id, label)
            uqk = user_queue_key(room_id)

            all_users = await self._r.lrange(src_list, 0, -1)
            to_move = all_users[len(all_users) // 2 :]
            if to_move:
                tickets = await self._r.hmget(src_hash, to_move)
                async with self._r.pipeline(transaction=True) as pipe:
                    for user, ticket in zip(to_move, tickets, strict=False):
                        if ticket:
                            pipe.lrem(src_list, 0, user)
                            pipe.hdel(src_hash, user)
                            pipe.rpush(dst_list, user)
                            pipe.hset(dst_hash, user, ticket)
                            pipe.hset(uqk, user, label)
                    await pipe.execute()
        return True

    async def remove_queue(self, room_id: str, label: str) -> bool:
        existing = await self.get_queues(room_id)
        if len(existing) <= 1:
            raise ValueError("last_queue")
        if label not in existing:
            return False

        remaining = [lbl for lbl in existing if lbl != label]
        src_list = queue_list_key(room_id, label)
        src_hash = queue_hash_key(room_id, label)
        uqk = user_queue_key(room_id)

        waiting_users = await self._r.lrange(src_list, 0, -1)
        if waiting_users:
            tickets = await self._r.hmget(src_hash, waiting_users)
            lengths = {lbl: await self._r.llen(queue_list_key(room_id, lbl)) for lbl in remaining}
            async with self._r.pipeline(transaction=True) as pipe:
                for user, ticket in zip(waiting_users, tickets, strict=False):
                    if ticket:
                        dst = min(lengths, key=lambda lbl: lengths[lbl])
                        pipe.rpush(queue_list_key(room_id, dst), user)
                        pipe.hset(queue_hash_key(room_id, dst), user, ticket)
                        pipe.hset(uqk, user, dst)
                        lengths[dst] += 1
                await pipe.execute()

        for k in [src_list, src_hash, queue_current_key(room_id, label)]:
            await self._r.delete(k)
        await self._r.lrem(room_queues_key(room_id), 0, label)
        return True

    async def close_room_keys(self, room_id: str) -> None:
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
        for k in keys:
            await self._r.delete(k)

    async def pick_shortest_queue(self, room_id: str) -> str:
        labels = await self.get_queues(room_id)
        async with self._r.pipeline(transaction=False) as pipe:
            for label in labels:
                pipe.llen(queue_list_key(room_id, label))
                pipe.hgetall(queue_current_key(room_id, label))
            results = await pipe.execute()
        lengths = []
        for i, _label in enumerate(labels):
            waiting = results[i * 2]
            current = results[i * 2 + 1]
            serving = 1 if current.get("status") == "serving" else 0
            lengths.append(waiting + serving)
        return labels[lengths.index(min(lengths))]

    async def get_user_queue(self, room_id: str, fingerprint: str) -> str | None:
        mapping = await self._r.hgetall(user_queue_key(room_id))
        return mapping.get(fingerprint)

    async def get_existing_ticket(
        self, room_id: str, fingerprint: str
    ) -> tuple[str, str, int | None] | None:
        uqk = user_queue_key(room_id)
        mapping = await self._r.hgetall(uqk)
        label = mapping.get(fingerprint)
        if not label:
            return None
        hk = queue_hash_key(room_id, label)
        lk = queue_list_key(room_id, label)
        ticket = await self._r.hget(hk, fingerprint)
        if not ticket:
            await self._r.hdel(uqk, fingerprint)
            return None
        pos = await self._r.lpos(lk, fingerprint)
        return label, ticket, (pos + 1) if pos is not None else None

    async def take_ticket(self, room_id: str, label: str, fingerprint: str) -> tuple[str, int]:
        hk = queue_hash_key(room_id, label)
        lk = queue_list_key(room_id, label)
        uqk = user_queue_key(room_id)

        num = await self._r.incr(queue_counter_key(room_id, label))
        ticket_code = f"{label}{num}"

        async with self._r.pipeline(transaction=True) as pipe:
            pipe.hset(hk, fingerprint, ticket_code)
            pipe.rpush(lk, fingerprint)
            pipe.hset(uqk, fingerprint, label)
            pipe.expire(hk, self._ttl)
            pipe.expire(lk, self._ttl)
            pipe.expire(uqk, self._ttl)
            pipe.expire(queue_counter_key(room_id, label), self._ttl)
            await pipe.execute()

        return ticket_code, num

    async def leave_queue(self, room_id: str, fingerprint: str) -> None:
        uqk = user_queue_key(room_id)
        mapping = await self._r.hgetall(uqk)
        label = mapping.get(fingerprint)
        if label:
            async with self._r.pipeline(transaction=True) as pipe:
                pipe.lrem(queue_list_key(room_id, label), 0, fingerprint)
                pipe.hdel(queue_hash_key(room_id, label), fingerprint)
                pipe.hdel(uqk, fingerprint)
                await pipe.execute()

            current = await self._r.hgetall(queue_current_key(room_id, label))
            if current.get("active_user_id") == fingerprint:
                await self._r.hset(
                    queue_current_key(room_id, label),
                    mapping={"status": "waiting", "ticket": "", "active_user_id": ""},
                )

    async def call_next(self, room_id: str, label: str) -> tuple[str, str, str]:
        lk = queue_list_key(room_id, label)
        hk = queue_hash_key(room_id, label)
        ck = queue_current_key(room_id, label)

        if not await self._r.llen(lk):
            raise ValueError("empty")

        served_user = await self._r.lpop(lk)
        ticket = await self._r.hget(hk, served_user)
        await self._r.hdel(hk, served_user)

        started_at = str(time.time())
        await self._r.hset(
            ck,
            mapping={
                "status": "serving",
                "ticket": ticket,
                "active_user_id": served_user,
                "started_at": started_at,
            },
        )
        return served_user, ticket, started_at

    async def complete_serving(self, room_id: str, label: str) -> tuple[str, str, str, int]:
        ck = queue_current_key(room_id, label)
        current = await self._r.hgetall(ck)
        if current.get("status") != "serving":
            raise ValueError("not_serving")

        ticket = current.get("ticket", "")
        served_user = current.get("active_user_id", "")
        started_at = current.get("started_at", "")

        await self._r.hset(ck, mapping={"status": "waiting", "ticket": "", "active_user_id": ""})
        if served_user:
            await self._r.hdel(user_queue_key(room_id), served_user)

        serve_seconds = 0
        with contextlib.suppress(ValueError):
            serve_seconds = int(time.time() - float(started_at)) if started_at else 0

        return ticket, served_user, started_at, serve_seconds

    async def update_avg_serve(self, room_id: str, serve_seconds: int) -> None:
        avg_key = room_avg_serve_key(room_id)
        cnt_key = room_serve_count_key(room_id)
        prev_avg = await self._r.get(avg_key)
        prev_cnt = await self._r.get(cnt_key)
        count = int(prev_cnt) + 1 if prev_cnt else 1
        if prev_avg is None:
            new_avg = serve_seconds
        else:
            new_avg = int(float(prev_avg) + (serve_seconds - float(prev_avg)) / count)
        async with self._r.pipeline() as pipe:
            pipe.set(avg_key, new_avg, ex=self._ttl)
            pipe.set(cnt_key, count, ex=self._ttl)
            await pipe.execute()

    async def get_state(self, room_id: str, user_id: str = "") -> dict:
        labels = await self.get_queues(room_id)

        async with self._r.pipeline(transaction=False) as pipe:
            pipe.exists(queue_current_key(room_id, labels[0]))
            pipe.hgetall(user_queue_key(room_id))
            pipe.get(room_avg_serve_key(room_id))
            for label in labels:
                pipe.hgetall(queue_current_key(room_id, label))
                pipe.lrange(queue_list_key(room_id, label), 0, -1)
            results = await pipe.execute()

        exists = results[0]
        if not exists:
            return {"room_closed": True, "room_id": room_id}

        user_queue_map = results[1]
        avg_raw = results[2]
        user_label = user_queue_map.get(user_id)

        queue_infos = []
        my_ticket, my_queue, my_pos = "--", "", "Нет в очереди"
        my_status, my_elapsed = "waiting", 0
        global_elapsed = 0

        per_queue_offset = 3
        for i, label in enumerate(labels):
            current = results[per_queue_offset + i * 2]
            users_in_q = results[per_queue_offset + i * 2 + 1]

            if users_in_q:
                tickets = await self._r.hmget(queue_hash_key(room_id, label), users_in_q)
            else:
                tickets = []

            queue_list = [
                {"user_id": u, "ticket": t} for u, t in zip(users_in_q, tickets, strict=False) if t
            ]

            status = current.get("status", "waiting")
            current_ticket = current.get("ticket", "")
            active_user = current.get("active_user_id", "")
            label_elapsed = 0

            if status == "serving" and current.get("started_at"):
                with contextlib.suppress(ValueError):
                    label_elapsed = int(time.time() - float(current["started_at"]))
                    global_elapsed = max(global_elapsed, label_elapsed)

            queue_infos.append(
                {
                    "label": label,
                    "length": len(queue_list),
                    "status": status,
                    "current_ticket": f"№ {current_ticket}" if current_ticket else "ОЖИДАНИЕ",
                    "elapsed_time": label_elapsed,
                }
            )

            if status == "serving" and active_user == user_id:
                my_ticket = f"№ {current_ticket}"
                my_queue = label
                my_pos = "На приеме"
                my_status = "serving"
                my_elapsed = label_elapsed
            elif user_label == label:
                for idx, m in enumerate(queue_list):
                    if m["user_id"] == user_id:
                        my_ticket = f"№ {m['ticket']}"
                        my_queue = label
                        pos = idx + 1 + (1 if status == "serving" else 0)
                        my_pos = str(pos)
                        my_status = "waiting"
                        my_elapsed = 0
                        break

        avg_serve = int(avg_raw) if avg_raw else None

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


class RoomConnectionManager:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis
        self._connections: dict[str, set[tuple[WebSocket, str]]] = {}

    async def connect(self, room_id: str, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self._connections.setdefault(room_id, set()).add((websocket, user_id))
        asyncio.create_task(self._listen_pubsub(room_id, websocket))

    def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        if room_id in self._connections:
            self._connections[room_id] = {
                item for item in self._connections[room_id] if item[0] != websocket
            }
            if not self._connections[room_id]:
                del self._connections[room_id]

    async def _listen_pubsub(self, room_id: str, websocket: WebSocket) -> None:
        pubsub = self._r.pubsub()
        await pubsub.subscribe(f"room:{room_id}:updates")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except Exception:
            pass
        finally:
            await pubsub.unsubscribe()
            await pubsub.close()

    async def broadcast(self, room_id: str, payload: dict) -> None:
        await self._r.publish(f"room:{room_id}:updates", json.dumps(payload))
