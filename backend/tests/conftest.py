import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.domain.entities import Queue
from src.domain.repositories import (
    EventPublisher,
    QueueRepository,
    RoomRepository,
    TicketRepository,
)
from src.ioc import ServiceProvider
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


def make_queue_repo_mock() -> AsyncMock:
    mock = AsyncMock(spec=QueueRepository)
    mock.room_exists.return_value = True
    # По умолчанию владелец комнаты — test_admin (совпадает с sub в admin_token),
    # чтобы админ-эндпоинты проходили проверку владельца. Тесты, где нужен
    # другой владелец/его отсутствие, переопределяют это значение явно.
    mock.get_owner.return_value = "test_admin"
    mock.set_owner.return_value = None
    mock.load.return_value = Queue(label="A", room_id="ROOM01")
    mock.load_all.return_value = [Queue(label="A", room_id="ROOM01")]
    mock.save.return_value = None
    mock.delete.return_value = None
    mock.delete_all.return_value = None
    mock.get_avg_serve.return_value = None
    mock.update_avg_serve.return_value = None
    mock.get_room_flags.return_value = {"is_open": True, "balancer_enabled": True}
    mock.set_room_flags.return_value = None
    mock.find_label_by_code.return_value = None
    mock.is_admin.return_value = True
    mock.add_admin.return_value = None
    mock.remove_admin.return_value = None
    mock.create_invite.return_value = None
    mock.consume_invite.return_value = True

    # lock(room_id) — синхронный метод, возвращающий async-контекст-менеджер.
    # Подменяем no-op контекстом, чтобы `async with repo.lock(...)` работал в юнит-тестах.
    @contextlib.asynccontextmanager
    async def _noop_lock(_room_id):
        yield

    mock.lock = MagicMock(side_effect=_noop_lock)
    return mock


def make_room_repo_mock() -> AsyncMock:
    return AsyncMock(spec=RoomRepository)


def make_ticket_repo_mock() -> AsyncMock:
    mock = AsyncMock(spec=TicketRepository)
    mock.load_history.return_value = []
    return mock


def make_publisher_mock() -> MagicMock:
    mock = MagicMock(spec=EventPublisher)
    mock.publish = AsyncMock()
    mock.connect = AsyncMock()
    mock.disconnect = MagicMock()
    return mock


@pytest.fixture
def mock_queue_repo():
    return make_queue_repo_mock()


@pytest.fixture
def mock_room_repo():
    return make_room_repo_mock()


@pytest.fixture
def mock_ticket_repo():
    return make_ticket_repo_mock()


@pytest.fixture
def mock_publisher():
    return make_publisher_mock()


@pytest.fixture
async def client(mock_queue_repo, mock_room_repo, mock_ticket_repo, mock_publisher):
    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def settings(self) -> Settings:
            return _settings

        @provide
        def queue_repo(self) -> QueueRepository:
            return mock_queue_repo

        @provide
        def room_repo(self) -> RoomRepository:
            return mock_room_repo

        @provide
        def ticket_repo(self) -> TicketRepository:
            return mock_ticket_repo

        @provide
        def publisher(self) -> EventPublisher:
            return mock_publisher

    test_container = make_async_container(TestProvider(), ServiceProvider())

    from src.main import app as _app

    original_container = _app.state.dishka_container
    _app.state.dishka_container = test_container
    try:
        async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as ac:
            yield ac
    finally:
        await test_container.close()
        _app.state.dishka_container = original_container
