from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.config import Settings
from src.domain.entities import Ticket, TicketRecord
from src.domain.repositories import EventPublisher
from src.infrastructure.db.base import init_db
from src.infrastructure.db.repositories import (
    SQLAlchemyRoomRepository,
    SQLAlchemyTicketRepository,
)
from src.infrastructure.redis.queue_repo import RedisQueueRepository
from src.services.auth import AuthService
from src.services.room import RoomService
from src.services.visitor import VisitorService

REDIS_URL = "redis://localhost:6379/1"
QUEUE_TTL = 60


class SessionPerCallTicketRepository:
    """Тестовый тикет-репозиторий: открывает свежую сессию на каждый вызов.

    В проде dishka выдаёт каждой HTTP-сессии собственный AsyncSession (request
    scope). Чтобы интеграционные тесты с конкурентными вызовами не делили одну
    сессию (что вызывает IllegalStateChangeError), повторяем здесь то же
    поведение поверх sessionmaker.
    """

    def __init__(self, factory: async_sessionmaker) -> None:
        self._factory = factory

    async def save(self, ticket: Ticket) -> None:
        async with self._factory() as s:
            await SQLAlchemyTicketRepository(s).save(ticket)

    async def mark_called(self, room_id, queue_label, num, at: datetime) -> None:
        async with self._factory() as s:
            await SQLAlchemyTicketRepository(s).mark_called(room_id, queue_label, num, at)

    async def mark_completed(self, room_id, queue_label, num, at: datetime) -> None:
        async with self._factory() as s:
            await SQLAlchemyTicketRepository(s).mark_completed(room_id, queue_label, num, at)

    async def load_history(self, room_id) -> list[TicketRecord]:
        async with self._factory() as s:
            return await SQLAlchemyTicketRepository(s).load_history(room_id)


@pytest.fixture
async def redis_client():
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def queue_repo(redis_client) -> RedisQueueRepository:
    return RedisQueueRepository(redis_client, QUEUE_TTL)


@pytest.fixture
async def session_factory():
    # Один shared in-memory engine на тест, чтобы все сессии видели одни таблицы.
    # StaticPool + один connection: все сессии делят одну in-memory БД.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def ticket_repo(session_factory) -> SessionPerCallTicketRepository:
    return SessionPerCallTicketRepository(session_factory)


@pytest.fixture
async def room_repo(session_factory) -> SQLAlchemyRoomRepository:
    async with session_factory() as session:
        yield SQLAlchemyRoomRepository(session)


@pytest.fixture
def publisher() -> MagicMock:
    pub = MagicMock(spec=EventPublisher)
    pub.publish = AsyncMock()
    pub.connect = AsyncMock()
    pub.disconnect = MagicMock()
    return pub


@pytest.fixture
def auth_service() -> AuthService:
    return AuthService(Settings())


@pytest.fixture
def room_service(queue_repo, room_repo, ticket_repo, auth_service, publisher) -> RoomService:
    return RoomService(queue_repo, room_repo, ticket_repo, auth_service, publisher, Settings())


@pytest.fixture
def visitor_service(queue_repo, ticket_repo, auth_service, publisher) -> VisitorService:
    return VisitorService(queue_repo, ticket_repo, auth_service, publisher)
