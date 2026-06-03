"""Юнит-тесты новых фич: конфиг комнаты, приём open/closed, балансировщик off,
коды очередей, пропуск, перемещение талона, статусы посетителя."""

from src.domain.entities import Queue, Ticket

# ---------------------------------------------------------------------------
# Конфиг комнаты при создании (feature 1 + 4)
# ---------------------------------------------------------------------------


async def test_create_room_default_open_balanced(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = False

    resp = await client.post("/api/v1/rooms", headers=user_headers)

    assert resp.status_code == 200
    # Дефолтные флаги выставлены в Redis.
    mock_queue_repo.set_room_flags.assert_awaited()
    kwargs = mock_queue_repo.set_room_flags.call_args.kwargs
    assert kwargs == {"is_open": True, "balancer_enabled": True}


async def test_create_room_closed_no_balancer(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = False

    resp = await client.post(
        "/api/v1/rooms",
        json={"is_open": False, "balancer_enabled": False},
        headers=user_headers,
    )

    assert resp.status_code == 200
    kwargs = mock_queue_repo.set_room_flags.call_args.kwargs
    assert kwargs == {"is_open": False, "balancer_enabled": False}


async def test_create_room_default_queue_has_code(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = False

    await client.post("/api/v1/rooms", headers=user_headers)

    saved = [c.args[0] for c in mock_queue_repo.save.call_args_list if isinstance(c.args[0], Queue)]
    assert saved and saved[0].code, "у дефолтной очереди должен быть код"


# ---------------------------------------------------------------------------
# Приём открыт/закрыт (feature 1)
# ---------------------------------------------------------------------------


async def test_take_ticket_rejected_when_closed(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.get_owner.return_value = "other"
    mock_queue_repo.get_room_flags.return_value = {"is_open": False, "balancer_enabled": True}
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]

    resp = await client.post(
        "/api/v1/queue/ticket", json={"room_id": "ROOM01"}, headers=user_headers
    )

    assert resp.status_code == 403
    assert "закрыт" in resp.json()["detail"].lower()


async def test_existing_user_not_rejected_when_closed(client, user_headers, mock_queue_repo):
    # Уже стоящий в очереди видит свой талон даже после закрытия приёма.
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.get_owner.return_value = "other"
    mock_queue_repo.get_room_flags.return_value = {"is_open": False, "balancer_enabled": True}
    ticket = Ticket(num="A1", user_id="test_user", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01", waiting=[ticket])]

    resp = await client.post(
        "/api/v1/queue/ticket", json={"room_id": "ROOM01"}, headers=user_headers
    )

    assert resp.status_code == 200
    assert resp.json()["ticket"] == "A1"


async def test_toggle_entry_open(client, admin_headers, mock_queue_repo):
    resp = await client.post(
        "/api/v1/admin/entry", json={"room_id": "ROOM01", "is_open": True}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_open"] is True
    mock_queue_repo.set_room_flags.assert_awaited_with("ROOM01", is_open=True)


async def test_toggle_entry_requires_admin(client, admin_headers, mock_queue_repo):
    # Не владелец и не со-админ — доступ запрещён.
    mock_queue_repo.is_admin.return_value = False
    resp = await client.post(
        "/api/v1/admin/entry", json={"room_id": "ROOM01", "is_open": True}, headers=admin_headers
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Балансировщик off (feature 4)
# ---------------------------------------------------------------------------


async def test_balancer_off_no_code_routes_to_some_queue(client, user_headers, mock_queue_repo):
    # VIP-режим, вход по общей ссылке без кода → кидаем в случайную очередь
    # (а не тупик). Главное — талон выдан в одну из существующих очередей.
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.get_owner.return_value = "other"
    mock_queue_repo.get_room_flags.return_value = {"is_open": True, "balancer_enabled": False}
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]

    resp = await client.post(
        "/api/v1/queue/ticket", json={"room_id": "ROOM01"}, headers=user_headers
    )

    assert resp.status_code == 200
    assert resp.json()["queue_label"] in {"A", "B"}


async def test_join_by_queue_code(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.get_owner.return_value = "other"
    mock_queue_repo.get_room_flags.return_value = {"is_open": True, "balancer_enabled": False}
    mock_queue_repo.find_label_by_code.return_value = "B"
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]

    resp = await client.post(
        "/api/v1/queue/ticket",
        json={"room_id": "ROOM01", "queue_code": "X7K2"},
        headers=user_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["queue_label"] == "B"


async def test_join_invalid_code(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.get_owner.return_value = "other"
    mock_queue_repo.find_label_by_code.return_value = None
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]

    resp = await client.post(
        "/api/v1/queue/ticket",
        json={"room_id": "ROOM01", "queue_code": "ZZZZ"},
        headers=user_headers,
    )

    assert resp.status_code == 404


async def test_toggle_balancer(client, admin_headers, mock_queue_repo):
    resp = await client.post(
        "/api/v1/admin/balancer",
        json={"room_id": "ROOM01", "enabled": False},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["balancer_enabled"] is False
    mock_queue_repo.set_room_flags.assert_awaited_with("ROOM01", balancer_enabled=False)


# ---------------------------------------------------------------------------
# add_queue возвращает код (feature 4)
# ---------------------------------------------------------------------------


async def test_add_queue_returns_code(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]

    resp = await client.post(
        "/api/v1/admin/queue/add", json={"room_id": "ROOM01"}, headers=admin_headers
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["queue_label"] == "B"
    assert data["code"], "новая очередь должна иметь код для прямого входа"


# ---------------------------------------------------------------------------
# Пропуск (feature 8) — не засчитывается в статистику
# ---------------------------------------------------------------------------


async def test_skip_clears_serving_without_completing(
    client, admin_headers, mock_queue_repo, mock_ticket_repo
):
    from datetime import UTC, datetime

    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", serving=ticket, serving_since=datetime.now(UTC))
    mock_queue_repo.load.return_value = queue

    resp = await client.post(
        "/api/v1/admin/skip", json={"room_id": "ROOM01", "queue_label": "A"}, headers=admin_headers
    )

    assert resp.status_code == 200
    saved = mock_queue_repo.save.call_args[0][0]
    assert saved.serving is None
    # Ключевое: не помечаем completed и не трогаем среднее время.
    mock_ticket_repo.mark_completed.assert_not_awaited()
    mock_queue_repo.update_avg_serve.assert_not_awaited()


async def test_skip_not_active_returns_400(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load.return_value = Queue(label="A", room_id="ROOM01", serving=None)
    resp = await client.post(
        "/api/v1/admin/skip", json={"room_id": "ROOM01", "queue_label": "A"}, headers=admin_headers
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Перемещение талона (feature 5)
# ---------------------------------------------------------------------------


async def test_move_ticket_within_queue(client, admin_headers, mock_queue_repo):
    tickets = [
        Ticket(num=f"A{i}", user_id=f"u{i}", queue_label="A", room_id="ROOM01") for i in range(1, 4)
    ]
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01", waiting=tickets)]

    resp = await client.post(
        "/api/v1/admin/move",
        json={"room_id": "ROOM01", "ticket": "A3", "to_queue": "A", "to_index": 0},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    saved = mock_queue_repo.save.call_args[0][0]
    assert saved.waiting[0].num == "A3"


async def test_move_ticket_between_queues(client, admin_headers, mock_queue_repo):
    a = Queue(
        label="A",
        room_id="ROOM01",
        waiting=[Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")],
    )
    b = Queue(label="B", room_id="ROOM01")
    mock_queue_repo.load_all.return_value = [a, b]

    resp = await client.post(
        "/api/v1/admin/move",
        json={"room_id": "ROOM01", "ticket": "A1", "to_queue": "B", "to_index": 0},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    saved = {c.args[0].label: c.args[0] for c in mock_queue_repo.save.call_args_list}
    assert len(saved["A"].waiting) == 0
    assert saved["B"].waiting[0].num == "A1"
    assert saved["B"].waiting[0].queue_label == "B"


async def test_move_unknown_ticket_404(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]
    resp = await client.post(
        "/api/v1/admin/move",
        json={"room_id": "ROOM01", "ticket": "Z9", "to_queue": "A", "to_index": 0},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Статус посетителя (feature 9)
# ---------------------------------------------------------------------------


async def test_set_status_on_way(client, user_headers, mock_queue_repo):
    ticket = Ticket(num="A1", user_id="test_user", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01", waiting=[ticket])]

    resp = await client.post(
        "/api/v1/queue/status",
        json={"room_id": "ROOM01", "status": "on_way"},
        headers=user_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "on_way"
    saved = mock_queue_repo.save.call_args[0][0]
    assert saved.waiting[0].status == "on_way"


async def test_set_status_rejects_unknown(client, user_headers, mock_queue_repo):
    resp = await client.post(
        "/api/v1/queue/status",
        json={"room_id": "ROOM01", "status": "teleporting"},
        headers=user_headers,
    )
    # Отклоняется на уровне схемы (pattern).
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# get_state раскрывает новые поля
# ---------------------------------------------------------------------------


async def test_state_exposes_flags_and_codes(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.get_room_flags.return_value = {"is_open": False, "balancer_enabled": False}
    mock_queue_repo.get_avg_serve.return_value = None
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01", code="X7K2")]

    resp = await client.get("/api/v1/rooms/ROOM01/state", headers=user_headers)

    data = resp.json()
    assert data["is_open"] is False
    assert data["balancer_enabled"] is False
    assert data["admin_context"]["queues"][0]["code"] == "X7K2"


async def test_state_exposes_waiting_detail_with_status(client, user_headers, mock_queue_repo):
    from src.domain.entities import TICKET_ON_WAY

    t1 = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01", status=TICKET_ON_WAY)
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.get_avg_serve.return_value = None
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01", waiting=[t1])]

    resp = await client.get("/api/v1/rooms/ROOM01/state", headers=user_headers)

    waiting = resp.json()["admin_context"]["queues"][0]["waiting"]
    assert waiting[0]["ticket"] == "A1"
    assert waiting[0]["status"] == "on_way"


# ---------------------------------------------------------------------------
# Со-администраторы по приглашению
# ---------------------------------------------------------------------------


async def test_owner_creates_invite(client, admin_headers, mock_queue_repo):
    resp = await client.post(
        "/api/v1/admin/invite", json={"room_id": "ROOM01"}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["token"]
    mock_queue_repo.create_invite.assert_awaited_once()


async def test_non_owner_cannot_create_invite(client, admin_headers, mock_queue_repo):
    mock_queue_repo.is_admin.return_value = False  # не владелец
    mock_queue_repo.get_owner.return_value = "someone_else"
    resp = await client.post(
        "/api/v1/admin/invite", json={"room_id": "ROOM01"}, headers=admin_headers
    )
    assert resp.status_code == 403


async def test_accept_invite_grants_admin_token(client, user_headers, mock_queue_repo):
    from tests.conftest import decode_token

    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.is_admin.return_value = False  # ещё не админ
    mock_queue_repo.consume_invite.return_value = True

    resp = await client.post(
        "/api/v1/admin/accept-invite",
        json={"room_id": "ROOM01", "token": "valid-invite-token"},
        headers=user_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    payload = decode_token(data["access_token"])
    assert payload["role"] == "admin"
    assert payload["room_id"] == "ROOM01"
    mock_queue_repo.add_admin.assert_awaited_once_with("ROOM01", "test_user")


async def test_accept_invalid_invite_rejected(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.is_admin.return_value = False  # не админ → нужен валидный токен
    mock_queue_repo.consume_invite.return_value = False

    resp = await client.post(
        "/api/v1/admin/accept-invite",
        json={"room_id": "ROOM01", "token": "bad-invite-token"},
        headers=user_headers,
    )
    assert resp.status_code == 400


async def test_accept_invite_idempotent_when_already_admin(client, user_headers, mock_queue_repo):
    # Повторный клик / двойной вызов: уже админ → выдаём токен без ошибки,
    # даже если приглашение уже погашено.
    from tests.conftest import decode_token

    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.is_admin.return_value = True
    mock_queue_repo.consume_invite.return_value = False  # токен уже использован

    resp = await client.post(
        "/api/v1/admin/accept-invite",
        json={"room_id": "ROOM01", "token": "used-token"},
        headers=user_headers,
    )

    assert resp.status_code == 200
    payload = decode_token(resp.json()["access_token"])
    assert payload["role"] == "admin"


async def test_resume_admin_returns_token_no_ticket(client, user_headers, mock_queue_repo):
    from tests.conftest import decode_token

    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.is_admin.return_value = True
    mock_queue_repo.get_owner.return_value = "test_user"

    resp = await client.post(
        "/api/v1/admin/resume", json={"room_id": "ROOM01"}, headers=user_headers
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_owner"] is True
    payload = decode_token(data["access_token"])
    assert payload["role"] == "admin"
    # resume не должен трогать очереди (никаких save).
    mock_queue_repo.save.assert_not_awaited()


async def test_resume_rejects_non_admin(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = True
    mock_queue_repo.is_admin.return_value = False
    resp = await client.post(
        "/api/v1/admin/resume", json={"room_id": "ROOM01"}, headers=user_headers
    )
    assert resp.status_code == 403


async def test_co_admin_can_call_next(client, user_headers, mock_queue_repo):
    # Пользователь принял приглашение → он в admins set → is_admin True.
    # Но admin-эндпоинты требуют admin-роль в токене; проверяем через сервисный
    # путь: токен админский (room_id совпадает) и is_admin True.
    from tests.conftest import create_token

    co_token = create_token("co_admin", role="admin", room_id="ROOM01")
    mock_queue_repo.is_admin.return_value = True
    mock_queue_repo.load.return_value = Queue(
        label="A",
        room_id="ROOM01",
        waiting=[Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")],
    )

    resp = await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers={"Authorization": f"Bearer {co_token}"},
    )

    assert resp.status_code == 200
