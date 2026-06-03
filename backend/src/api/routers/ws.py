import json
import logging
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.domain.repositories import EventPublisher
from src.services.auth import AuthService
from src.services.room import RoomService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


@router.websocket("/ws/room/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: Annotated[str | None, Query()] = None,
):
    room_id = room_id.upper().strip()

    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return

    app_container = websocket.app.state.dishka_container

    auth_service: AuthService = await app_container.get(AuthService)

    try:
        payload = auth_service.decode_token(token)
    except Exception:
        await websocket.close(code=4401, reason="Invalid token")
        return

    if payload.get("type") != "access":
        await websocket.close(code=4401, reason="Invalid token type")
        return

    user_id: str = payload.get("sub", "unknown")

    async with app_container() as request_container:
        room_service: RoomService = await request_container.get(RoomService)
        publisher: EventPublisher = await request_container.get(EventPublisher)

        await publisher.connect(room_id, websocket, user_id)

        try:
            state = await room_service.get_state(room_id, user_id)
            await websocket.send_text(json.dumps({"type": "welcome", "data": state}))

            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("WS error: %s", e)
        finally:
            # Гарантированно снимаем подписку и отменяем pubsub-таск,
            # даже если соединение упало неожиданно.
            publisher.disconnect(room_id, websocket)
