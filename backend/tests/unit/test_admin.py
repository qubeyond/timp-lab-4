from src.domain.entities import Queue, Ticket


async def test_call_next_success(client, admin_headers, mock_queue_repo, mock_ticket_repo):
    ticket = Ticket(num="A7", user_id="u1", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", waiting=[ticket])
    mock_queue_repo.load.return_value = queue
    resp = await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "called"
    assert data["ticket"] == "A7"
    assert data["queue_label"] == "A"


async def test_call_next_empty_queue(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load.return_value = Queue(label="A", room_id="ROOM01", waiting=[])
    resp = await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "пуста" in resp.json()["detail"].lower()


async def test_call_next_wrong_room(client, admin_headers):
    resp = await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM99", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 403


async def test_call_next_no_auth(client):
    resp = await client.post("/api/v1/admin/next", json={"room_id": "ROOM01", "queue_label": "A"})
    assert resp.status_code == 401


async def test_call_next_user_role_forbidden(client, user_headers):
    resp = await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=user_headers,
    )
    assert resp.status_code == 403


async def test_complete_serving_success(client, admin_headers, mock_queue_repo, mock_ticket_repo):
    from datetime import UTC, datetime

    ticket = Ticket(num="A7", user_id="u1", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", serving=ticket, serving_since=datetime.now(UTC))
    mock_queue_repo.load.return_value = queue
    resp = await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_complete_serving_not_active(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load.return_value = Queue(label="A", room_id="ROOM01", serving=None)
    resp = await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_complete_wrong_room(client, admin_headers):
    resp = await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM99", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 403


async def test_add_queue_success(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]
    resp = await client.post(
        "/api/v1/admin/queue/add",
        json={"room_id": "ROOM01"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["queue_label"] == "B"


async def test_add_queue_rebalances_users(client, admin_headers, mock_queue_repo):
    tickets = [
        Ticket(num=f"A{i}", user_id=f"u{i}", queue_label="A", room_id="ROOM01") for i in range(1, 5)
    ]
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01", waiting=tickets)]
    resp = await client.post(
        "/api/v1/admin/queue/add",
        json={"room_id": "ROOM01"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["queue_label"] == "B"
    assert mock_queue_repo.save.call_count >= 2

    saved_calls = {call.args[0].label: call.args[0] for call in mock_queue_repo.save.call_args_list}
    queue_b = saved_calls["B"]
    assert len(queue_b.waiting) == 2
    for ticket in queue_b.waiting:
        assert ticket.queue_label == "B", (
            f"ticket {ticket.num} still has old label {ticket.queue_label}"
        )


async def test_add_queue_rebalance_ticket_counter_updated(client, admin_headers, mock_queue_repo):
    tickets = [
        Ticket(num=f"A{i}", user_id=f"u{i}", queue_label="A", room_id="ROOM01") for i in range(1, 5)
    ]
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01", waiting=tickets, ticket_counter=4)
    ]
    resp = await client.post(
        "/api/v1/admin/queue/add",
        json={"room_id": "ROOM01"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    saved_calls = {call.args[0].label: call.args[0] for call in mock_queue_repo.save.call_args_list}
    queue_b = saved_calls["B"]
    assert queue_b.ticket_counter == len(queue_b.waiting)


async def test_add_queue_single_waiting_stays_put(client, admin_headers, mock_queue_repo):
    """Регрессия: при ОДНОМ ожидающем в A создание B НЕ должно опустошать A.

    Старый баг: единственный ожидающий перекидывался в новую очередь, A пустела.
    Корректно: переносить нечего (1 // 2 == 0), человек остаётся в A, B пустая.
    """
    waiting = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01", waiting=[waiting], ticket_counter=1)
    ]
    resp = await client.post(
        "/api/v1/admin/queue/add",
        json={"room_id": "ROOM01"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    saved_calls = {call.args[0].label: call.args[0] for call in mock_queue_repo.save.call_args_list}

    # B сохранена и пуста.
    assert "B" in saved_calls
    queue_b = saved_calls["B"]
    assert len(queue_b.waiting) == 0

    # A либо не пересохранялась (перенос пропущен), либо сохранена с тем же человеком.
    if "A" in saved_calls:
        queue_a = saved_calls["A"]
        assert len(queue_a.waiting) == 1
        assert queue_a.waiting[0].user_id == "u1"
        assert queue_a.waiting[0].queue_label == "A"


async def test_add_queue_single_waiting_does_not_resave_source(
    client, admin_headers, mock_queue_repo
):
    """При 1 ожидающем исходная очередь A не должна пересохраняться (нет переноса)."""
    waiting = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01", waiting=[waiting], ticket_counter=1)
    ]
    await client.post(
        "/api/v1/admin/queue/add",
        json={"room_id": "ROOM01"},
        headers=admin_headers,
    )
    saved_labels = [call.args[0].label for call in mock_queue_repo.save.call_args_list]
    assert "A" not in saved_labels, "очередь A не должна трогаться при единственном ожидающем"
    assert saved_labels.count("B") == 1


async def test_add_queue_max_reached(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [
        Queue(label=lbl, room_id="ROOM01") for lbl in "ABCDEFGHJK"
    ]
    resp = await client.post(
        "/api/v1/admin/queue/add",
        json={"room_id": "ROOM01"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_remove_queue_success(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]
    resp = await client.request(
        "DELETE",
        "/api/v1/admin/queue/remove",
        json={"room_id": "ROOM01", "queue_label": "B"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"


async def test_remove_queue_redistributes_users(client, admin_headers, mock_queue_repo):
    tickets = [
        Ticket(num="B1", user_id="u1", queue_label="B", room_id="ROOM01"),
        Ticket(num="B2", user_id="u2", queue_label="B", room_id="ROOM01"),
    ]
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01", waiting=tickets),
    ]
    resp = await client.request(
        "DELETE",
        "/api/v1/admin/queue/remove",
        json={"room_id": "ROOM01", "queue_label": "B"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    saved_queue = mock_queue_repo.save.call_args[0][0]
    assert len(saved_queue.waiting) == 2


async def test_remove_last_queue_forbidden(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]
    resp = await client.request(
        "DELETE",
        "/api/v1/admin/queue/remove",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_remove_nonexistent_queue(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]
    resp = await client.request(
        "DELETE",
        "/api/v1/admin/queue/remove",
        json={"room_id": "ROOM01", "queue_label": "C"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_call_next_rejects_stale_token_for_reused_room(
    client, admin_headers, mock_queue_repo
):
    """Регрессия: админ-токен валиден и room_id совпадает, но владелец в Redis
    другой (комната пересоздана) — мутация должна быть отклонена 403."""
    mock_queue_repo.get_owner.return_value = "another_admin"
    mock_queue_repo.load.return_value = Queue(
        label="A",
        room_id="ROOM01",
        waiting=[Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")],
    )
    resp = await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 403


async def test_add_queue_rejects_when_no_owner_in_redis(client, admin_headers, mock_queue_repo):
    """Комната истекла по TTL (нет владельца в Redis) — добавление очереди запрещено."""
    mock_queue_repo.get_owner.return_value = None
    resp = await client.post(
        "/api/v1/admin/queue/add",
        json={"room_id": "ROOM01"},
        headers=admin_headers,
    )
    assert resp.status_code == 403


async def test_stats_success(client, admin_headers, mock_ticket_repo):
    resp = await client.get("/api/v1/admin/stats/ROOM01", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_id"] == "ROOM01"
    assert "total_tickets" in data
    assert "completed" in data


async def test_stats_wrong_room(client, admin_headers):
    resp = await client.get("/api/v1/admin/stats/ROOM99", headers=admin_headers)
    assert resp.status_code == 403


async def test_stats_no_auth(client):
    resp = await client.get("/api/v1/admin/stats/ROOM01")
    assert resp.status_code == 401
