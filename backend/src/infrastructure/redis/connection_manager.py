import asyncio
import contextlib
import json
import logging

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)


MAX_CONNECTIONS_PER_USER = 5


class RoomConnectionManager:
    def __init__(self, redis: aioredis.Redis, max_connections_per_user: int = 5) -> None:
        self._r = redis
        self._max_conn = max_connections_per_user

        self._connections: dict[str, dict[WebSocket, tuple[str, asyncio.Task]]] = {}

    @property
    def max_connections_per_user(self) -> int:
        return self._max_conn

    def user_connection_count(self, user_id: str) -> int:
        return sum(
            1 for room in self._connections.values() for uid, _ in room.values() if uid == user_id
        )

    async def connect(self, room_id: str, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        task = asyncio.create_task(self._listen_pubsub(room_id, websocket))
        self._connections.setdefault(room_id, {})[websocket] = (user_id, task)

    def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        room = self._connections.get(room_id)
        if not room:
            return

        entry = room.pop(websocket, None)
        if entry is not None:
            _, task = entry

            task.cancel()

        if not room:
            del self._connections[room_id]

    async def _listen_pubsub(self, room_id: str, websocket: WebSocket) -> None:
        pubsub = self._r.pubsub()
        await pubsub.subscribe(f"room:{room_id}:updates")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("pubsub listener stopped for room %s: %s", room_id, e)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(f"room:{room_id}:updates")
            with contextlib.suppress(Exception):
                await pubsub.aclose()

    async def publish(self, room_id: str, payload: dict) -> None:
        await self._r.publish(f"room:{room_id}:updates", json.dumps(payload))
