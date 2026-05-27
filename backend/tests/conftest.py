from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.domain.repositories import QueueRepo, RoomRepo, TicketRepo, WebSocketBroadcaster
from src.infrastructure.ioc import ServiceProvider
from src.infrastructure.redis.queue_manager import RedisQueueRepo, RoomConnectionManager
from src.services.auth import AuthService

_settings = Settings()
_auth = AuthService(_settings)


def create_token(fingerprint: str, role: str = "user", room_id: str | None = None) -> str:
    return _auth.create_token(fingerprint, role=role, room_id=room_id)


def decode_token(token: str) -> dict:
    return _auth.decode_token(token)


@pytest.fixture
def user_token():
    return create_token(fingerprint="test_user", role="user")


@pytest.fixture
def admin_token():
    return create_token(fingerprint="test_admin", role="admin", room_id="ROOM01")


@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _make_redis_mock():
    mock = MagicMock()
    mock.exists = AsyncMock(return_value=1)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.hset = AsyncMock(return_value=1)
    mock.hget = AsyncMock(return_value=None)
    mock.hgetall = AsyncMock(return_value={})
    mock.hexists = AsyncMock(return_value=0)
    mock.hdel = AsyncMock(return_value=1)
    mock.llen = AsyncMock(return_value=0)
    mock.lrange = AsyncMock(return_value=[])
    mock.lpos = AsyncMock(return_value=None)
    mock.lpop = AsyncMock(return_value=None)
    mock.rpush = AsyncMock(return_value=1)
    mock.lrem = AsyncMock(return_value=1)
    mock.incr = AsyncMock(return_value=1)
    mock.delete = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.publish = AsyncMock(return_value=1)
    mock.hmget = AsyncMock(return_value=[])

    pipeline_mock = MagicMock()
    pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
    pipeline_mock.__aexit__ = AsyncMock(return_value=False)
    pipeline_mock.hset = MagicMock()
    pipeline_mock.rpush = MagicMock()
    pipeline_mock.lrem = MagicMock()
    pipeline_mock.hdel = MagicMock()
    pipeline_mock.expire = MagicMock()
    pipeline_mock.set = MagicMock()
    pipeline_mock._queued: list = []

    original_llen = mock.llen
    original_lrange = mock.lrange
    original_hgetall = mock.hgetall
    original_exists = mock.exists
    original_get = mock.get

    def pipe_llen(*a, **kw):
        pipeline_mock._queued.append(("llen", a, kw))

    def pipe_lrange(*a, **kw):
        pipeline_mock._queued.append(("lrange", a, kw))

    def pipe_hgetall(*a, **kw):
        pipeline_mock._queued.append(("hgetall", a, kw))

    def pipe_exists(*a, **kw):
        pipeline_mock._queued.append(("exists", a, kw))

    def pipe_get(*a, **kw):
        pipeline_mock._queued.append(("get", a, kw))

    pipeline_mock.llen = MagicMock(side_effect=pipe_llen)
    pipeline_mock.lrange = MagicMock(side_effect=pipe_lrange)
    pipeline_mock.hgetall = MagicMock(side_effect=pipe_hgetall)
    pipeline_mock.exists = MagicMock(side_effect=pipe_exists)
    pipeline_mock.get = MagicMock(side_effect=pipe_get)

    async def pipe_execute():
        results = []
        for cmd, args, kwargs in pipeline_mock._queued:
            if cmd == "llen":
                results.append(await original_llen(*args, **kwargs))
            elif cmd == "lrange":
                results.append(await original_lrange(*args, **kwargs))
            elif cmd == "hgetall":
                results.append(await original_hgetall(*args, **kwargs))
            elif cmd == "exists":
                results.append(await original_exists(*args, **kwargs))
            elif cmd == "get":
                results.append(await original_get(*args, **kwargs))
            else:
                results.append(1)
        pipeline_mock._queued.clear()
        return results

    pipeline_mock.execute = pipe_execute
    mock.pipeline = MagicMock(return_value=pipeline_mock)
    return mock


def _make_session_mock():
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    return _make_redis_mock()


@pytest.fixture
def mock_db():
    return _make_session_mock()


@pytest.fixture
async def client(mock_redis, mock_db):
    redis_mock = mock_redis
    db_mock = mock_db

    class TestInfraProvider(Provider):
        scope = Scope.APP

        @provide
        def settings(self) -> Settings:
            return _settings

        @provide
        def queue_repo(self) -> QueueRepo:
            return RedisQueueRepo(redis_mock, _settings.queue_ttl)

        @provide
        def broadcaster(self) -> WebSocketBroadcaster:
            return RoomConnectionManager(redis_mock)

    class TestSessionProvider(Provider):
        scope = Scope.REQUEST

        @provide
        async def session(self) -> AsyncIterator[AsyncSession]:
            yield db_mock

        @provide
        def room_repo(self, session: AsyncSession) -> RoomRepo:
            from src.infrastructure.db.repositories import SQLAlchemyRoomRepo

            return SQLAlchemyRoomRepo(session)

        @provide
        def ticket_repo(self, session: AsyncSession) -> TicketRepo:
            from src.infrastructure.db.repositories import SQLAlchemyTicketRepo

            return SQLAlchemyTicketRepo(session)

    test_container = make_async_container(
        TestInfraProvider(),
        TestSessionProvider(),
        ServiceProvider(),
    )

    from src.main import app as _app

    original_container = _app.state.dishka_container
    _app.state.dishka_container = test_container
    try:
        async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as ac:
            yield ac
    finally:
        await test_container.close()
        _app.state.dishka_container = original_container
