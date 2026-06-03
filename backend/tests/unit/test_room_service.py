from datetime import UTC, datetime

from src.domain.entities import Queue, Ticket

# ---------------------------------------------------------------------------
# create_room
# ---------------------------------------------------------------------------


async def test_create_room_saves_default_queue(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = False

    await client.post("/api/v1/rooms", headers=user_headers)

    saved_queues = [
        call.args[0]
        for call in mock_queue_repo.save.call_args_list
        if isinstance(call.args[0], Queue)
    ]
    assert any(q.label == "A" for q in saved_queues)


async def test_create_room_sets_owner(client, user_headers, mock_queue_repo):
    mock_queue_repo.room_exists.return_value = False

    resp = await client.post("/api/v1/rooms", headers=user_headers)

    assert resp.status_code == 200
    mock_queue_repo.set_owner.assert_awaited_once()
    owner_arg = mock_queue_repo.set_owner.call_args[0][1]
    assert owner_arg == "test_user"


async def test_create_room_token_expires_in_future(client, user_headers, mock_queue_repo):
    from tests.conftest import decode_token

    mock_queue_repo.room_exists.return_value = False

    resp = await client.post("/api/v1/rooms", headers=user_headers)

    payload = decode_token(resp.json()["access_token"])
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    assert exp > datetime.now(UTC)


# ---------------------------------------------------------------------------
# close_room
# ---------------------------------------------------------------------------


async def test_close_room_deletes_all_queues(client, admin_headers, mock_queue_repo):
    mock_queue_repo.get_owner.return_value = "test_admin"

    await client.delete("/api/v1/rooms/ROOM01", headers=admin_headers)

    mock_queue_repo.delete_all.assert_awaited_once_with("ROOM01")


async def test_close_room_publishes_closed_event(
    client, admin_headers, mock_queue_repo, mock_publisher
):
    mock_queue_repo.get_owner.return_value = "test_admin"

    await client.delete("/api/v1/rooms/ROOM01", headers=admin_headers)

    mock_publisher.publish.assert_awaited_once()
    payload = mock_publisher.publish.call_args[0][1]
    assert payload.get("data", {}).get("room_closed") is True


# ---------------------------------------------------------------------------
# add_queue — publish
# ---------------------------------------------------------------------------


async def test_add_queue_publishes_update(client, admin_headers, mock_queue_repo, mock_publisher):
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]

    await client.post("/api/v1/admin/queue/add", json={"room_id": "ROOM01"}, headers=admin_headers)

    mock_publisher.publish.assert_awaited_once()


async def test_add_queue_saves_new_queue(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [Queue(label="A", room_id="ROOM01")]

    await client.post("/api/v1/admin/queue/add", json={"room_id": "ROOM01"}, headers=admin_headers)

    saved_labels = [call.args[0].label for call in mock_queue_repo.save.call_args_list]
    assert "B" in saved_labels


async def test_add_queue_skips_existing_labels(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]

    resp = await client.post(
        "/api/v1/admin/queue/add", json={"room_id": "ROOM01"}, headers=admin_headers
    )

    assert resp.json()["queue_label"] == "C"


# ---------------------------------------------------------------------------
# remove_queue — redistribute
# ---------------------------------------------------------------------------


async def test_remove_queue_redistributes_to_multiple_remaining(
    client, admin_headers, mock_queue_repo
):
    t1 = Ticket(num="C1", user_id="u1", queue_label="C", room_id="ROOM01")
    t2 = Ticket(num="C2", user_id="u2", queue_label="C", room_id="ROOM01")
    t3 = Ticket(num="C3", user_id="u3", queue_label="C", room_id="ROOM01")
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
        Queue(label="C", room_id="ROOM01", waiting=[t1, t2, t3]),
    ]

    resp = await client.request(
        "DELETE",
        "/api/v1/admin/queue/remove",
        json={"room_id": "ROOM01", "queue_label": "C"},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    saved = {call.args[0].label: call.args[0] for call in mock_queue_repo.save.call_args_list}
    total_redistributed = sum(len(q.waiting) for q in saved.values() if q.label != "C")
    assert total_redistributed == 3


async def test_remove_queue_publishes_update(
    client, admin_headers, mock_queue_repo, mock_publisher
):
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]

    await client.request(
        "DELETE",
        "/api/v1/admin/queue/remove",
        json={"room_id": "ROOM01", "queue_label": "B"},
        headers=admin_headers,
    )

    mock_publisher.publish.assert_awaited_once()


async def test_remove_queue_deletes_from_repo(client, admin_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]

    await client.request(
        "DELETE",
        "/api/v1/admin/queue/remove",
        json={"room_id": "ROOM01", "queue_label": "B"},
        headers=admin_headers,
    )

    mock_queue_repo.delete.assert_awaited_once_with("ROOM01", "B")


# ---------------------------------------------------------------------------
# call_next
# ---------------------------------------------------------------------------


async def test_call_next_moves_ticket_to_serving(client, admin_headers, mock_queue_repo):
    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", waiting=[ticket])
    mock_queue_repo.load.return_value = queue

    resp = await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    saved_queue: Queue = mock_queue_repo.save.call_args[0][0]
    assert saved_queue.serving is not None
    assert saved_queue.serving.num == "A1"
    assert len(saved_queue.waiting) == 0


async def test_call_next_marks_ticket_called_in_repo(
    client, admin_headers, mock_queue_repo, mock_ticket_repo
):
    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load.return_value = Queue(label="A", room_id="ROOM01", waiting=[ticket])

    await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    mock_ticket_repo.mark_called.assert_awaited_once()
    args = mock_ticket_repo.mark_called.call_args[0]
    assert args[2] == "A1"


async def test_call_next_publishes_update(client, admin_headers, mock_queue_repo, mock_publisher):
    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load.return_value = Queue(label="A", room_id="ROOM01", waiting=[ticket])

    await client.post(
        "/api/v1/admin/next",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    mock_publisher.publish.assert_awaited_once()


# ---------------------------------------------------------------------------
# complete_serving
# ---------------------------------------------------------------------------


async def test_complete_serving_clears_serving_in_repo(client, admin_headers, mock_queue_repo):
    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", serving=ticket, serving_since=datetime.now(UTC))
    mock_queue_repo.load.return_value = queue

    await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    saved_queue: Queue = mock_queue_repo.save.call_args[0][0]
    assert saved_queue.serving is None


async def test_complete_serving_marks_completed_in_repo(
    client, admin_headers, mock_queue_repo, mock_ticket_repo
):
    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", serving=ticket, serving_since=datetime.now(UTC))
    mock_queue_repo.load.return_value = queue

    await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    mock_ticket_repo.mark_completed.assert_awaited_once()
    args = mock_ticket_repo.mark_completed.call_args[0]
    assert args[2] == "A1"


async def test_complete_serving_publishes_update(
    client, admin_headers, mock_queue_repo, mock_publisher
):
    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load.return_value = Queue(
        label="A", room_id="ROOM01", serving=ticket, serving_since=datetime.now(UTC)
    )

    await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    mock_publisher.publish.assert_awaited_once()


async def test_complete_serving_updates_avg(client, admin_headers, mock_queue_repo):
    """Регрессия: complete_serving должен обновлять среднее время обслуживания.

    Раньше update_avg_serve не вызывался нигде — среднее всегда оставалось 0.
    """
    from datetime import timedelta

    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    started = datetime.now(UTC) - timedelta(seconds=42)
    mock_queue_repo.load.return_value = Queue(
        label="A", room_id="ROOM01", serving=ticket, serving_since=started
    )

    await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    mock_queue_repo.update_avg_serve.assert_awaited_once()
    args = mock_queue_repo.update_avg_serve.call_args[0]
    assert args[0] == "ROOM01"
    assert args[1] >= 41  # ~42 секунды обслуживания


async def test_complete_serving_without_started_at_skips_avg(
    client, admin_headers, mock_queue_repo
):
    """Если serving_since отсутствует — среднее не обновляем (нечего считать)."""
    ticket = Ticket(num="A1", user_id="u1", queue_label="A", room_id="ROOM01")
    mock_queue_repo.load.return_value = Queue(
        label="A", room_id="ROOM01", serving=ticket, serving_since=None
    )

    await client.post(
        "/api/v1/admin/complete",
        json={"room_id": "ROOM01", "queue_label": "A"},
        headers=admin_headers,
    )

    mock_queue_repo.update_avg_serve.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------


async def test_get_state_shows_user_position(client, user_headers, mock_queue_repo):
    ticket = Ticket(num="A2", user_id="test_user", queue_label="A", room_id="ROOM01")
    other = Ticket(num="A1", user_id="x1", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", waiting=[other, ticket])
    mock_queue_repo.load_all.return_value = [queue]
    mock_queue_repo.get_avg_serve.return_value = None

    resp = await client.get("/api/v1/rooms/ROOM01/state", headers=user_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["client_context"]["position_label"] == "2"
    assert "A2" in data["client_context"]["ticket_label"]


async def test_get_state_serving_user_sees_no_position(client, user_headers, mock_queue_repo):
    ticket = Ticket(num="A1", user_id="test_user", queue_label="A", room_id="ROOM01")
    queue = Queue(label="A", room_id="ROOM01", serving=ticket, serving_since=datetime.now(UTC))
    mock_queue_repo.load_all.return_value = [queue]
    mock_queue_repo.get_avg_serve.return_value = None

    resp = await client.get("/api/v1/rooms/ROOM01/state", headers=user_headers)

    data = resp.json()
    assert data["current_status"] == "serving"
    assert data["client_context"]["position_label"] == "На приеме"


async def test_get_state_queue_info_reflects_all_queues(client, user_headers, mock_queue_repo):
    mock_queue_repo.load_all.return_value = [
        Queue(label="A", room_id="ROOM01"),
        Queue(label="B", room_id="ROOM01"),
    ]
    mock_queue_repo.get_avg_serve.return_value = None

    resp = await client.get("/api/v1/rooms/ROOM01/state", headers=user_headers)

    queues_info = resp.json()["admin_context"]["queues"]
    assert len(queues_info) == 2
    labels = {q["label"] for q in queues_info}
    assert labels == {"A", "B"}
