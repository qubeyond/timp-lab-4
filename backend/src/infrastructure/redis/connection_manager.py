import asyncio
import contextlib
import json
import logging

import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class RoomConnectionManager:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis
        # websocket -> (user_id, pubsub listener task)
        self._connections: dict[str, dict[WebSocket, tuple[str, asyncio.Task]]] = {}

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
            # Останавливаем зависший pubsub.listen(), иначе таск и подписка
            # на Redis-канал живут вечно и текут на каждом реконнекте.
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
