from datetime import UTC, datetime

import pytest

from src.domain.entities import (
    DEFAULT_QUEUE,
    MAX_QUEUES,
    QUEUE_LABELS,
    Queue,
    Room,
    Ticket,
    TicketRecord,
)

# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------


def test_ticket_build_num_first():
    assert Ticket.build_num("A", 0) == "A1"


def test_ticket_build_num_counter():
    assert Ticket.build_num("B", 9) == "B10"


# ---------------------------------------------------------------------------
# TicketRecord computed properties
# ---------------------------------------------------------------------------


def test_ticket_record_wait_seconds():
    joined = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    called = datetime(2024, 1, 1, 10, 5, 30, tzinfo=UTC)
    r = TicketRecord(num="A1", queue_label="A", joined_at=joined, called_at=called)

    assert r.wait_seconds == 330


def test_ticket_record_wait_seconds_none_when_not_called():
    r = TicketRecord(num="A1", queue_label="A", joined_at=datetime.now(UTC))

    assert r.wait_seconds is None


def test_ticket_record_serve_seconds():
    called = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
    completed = datetime(2024, 1, 1, 10, 3, 0, tzinfo=UTC)
    r = TicketRecord(
        num="A1", queue_label="A", joined_at=called, called_at=called, completed_at=completed
    )

    assert r.serve_seconds == 180


def test_ticket_record_serve_seconds_none_when_not_completed():
    called = datetime.now(UTC)
    r = TicketRecord(num="A1", queue_label="A", joined_at=called, called_at=called)

    assert r.serve_seconds is None


def test_ticket_record_is_frozen():
    r = TicketRecord(num="A1", queue_label="A", joined_at=datetime.now(UTC))

    with pytest.raises(AttributeError):
        r.num = "B1"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Queue — enqueue
# ---------------------------------------------------------------------------


def test_queue_enqueue_increments_counter():
    q = Queue(label="A", room_id="R1")

    q.enqueue("u1")

    assert q.ticket_counter == 1


def test_queue_enqueue_assigns_correct_num():
    q = Queue(label="A", room_id="R1")

    t = q.enqueue("u1")

    assert t.num == "A1"


def test_queue_enqueue_sequential_nums():
    q = Queue(label="A", room_id="R1")

    t1 = q.enqueue("u1")
    t2 = q.enqueue("u2")

    assert t1.num == "A1"
    assert t2.num == "A2"


def test_queue_enqueue_sets_labels():
    q = Queue(label="B", room_id="R1")

    t = q.enqueue("u1")

    assert t.queue_label == "B"
    assert t.room_id == "R1"


def test_queue_enqueue_appends_to_waiting():
    q = Queue(label="A", room_id="R1")

    q.enqueue("u1")
    q.enqueue("u2")

    assert len(q.waiting) == 2


# ---------------------------------------------------------------------------
# Queue — call_next
# ---------------------------------------------------------------------------


def test_queue_call_next_pops_first():
    q = Queue(label="A", room_id="R1")
    t1 = q.enqueue("u1")
    q.enqueue("u2")

    called = q.call_next(datetime.now(UTC))

    assert called.num == t1.num
    assert len(q.waiting) == 1


def test_queue_call_next_sets_serving():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")
    now = datetime.now(UTC)

    q.call_next(now)

    assert q.serving is not None
    assert q.serving_since == now


def test_queue_call_next_raises_on_empty():
    q = Queue(label="A", room_id="R1")

    with pytest.raises(ValueError):
        q.call_next(datetime.now(UTC))


def test_queue_call_next_replaces_previous_serving():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")
    q.enqueue("u2")
    now = datetime.now(UTC)

    first = q.call_next(now)
    second = q.call_next(now)

    assert q.serving.num == second.num
    assert first.num != second.num


# ---------------------------------------------------------------------------
# Queue — complete_serving
# ---------------------------------------------------------------------------


def test_queue_complete_serving_clears_serving():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")
    q.call_next(datetime.now(UTC))

    q.complete_serving()

    assert q.serving is None
    assert q.serving_since is None


def test_queue_complete_serving_returns_ticket():
    q = Queue(label="A", room_id="R1")
    t = q.enqueue("u1")
    q.call_next(datetime.now(UTC))

    done = q.complete_serving()

    assert done.num == t.num


def test_queue_complete_serving_raises_when_idle():
    q = Queue(label="A", room_id="R1")

    with pytest.raises(ValueError):
        q.complete_serving()


# ---------------------------------------------------------------------------
# Queue — dequeue
# ---------------------------------------------------------------------------


def test_queue_dequeue_removes_from_waiting():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")
    q.enqueue("u2")

    q.dequeue("u1")

    assert len(q.waiting) == 1
    assert q.waiting[0].user_id == "u2"


def test_queue_dequeue_clears_serving_if_active():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")
    q.call_next(datetime.now(UTC))

    q.dequeue("u1")

    assert q.serving is None


def test_queue_dequeue_unknown_user_returns_none():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")

    result = q.dequeue("nobody")

    assert result is None
    assert len(q.waiting) == 1


# ---------------------------------------------------------------------------
# Queue — find / position / has_user
# ---------------------------------------------------------------------------


def test_queue_find_ticket_in_waiting():
    q = Queue(label="A", room_id="R1")
    t = q.enqueue("u1")

    found = q.find_ticket("u1")

    assert found is not None
    assert found.num == t.num


def test_queue_find_ticket_being_served():
    q = Queue(label="A", room_id="R1")
    t = q.enqueue("u1")

    q.call_next(datetime.now(UTC))
    found = q.find_ticket("u1")

    assert found is not None
    assert found.num == t.num


def test_queue_find_ticket_returns_none_for_stranger():
    q = Queue(label="A", room_id="R1")

    assert q.find_ticket("nobody") is None


def test_queue_position_one_based():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")
    q.enqueue("u2")

    assert q.position("u1") == 1
    assert q.position("u2") == 2


def test_queue_position_none_when_serving():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")

    q.call_next(datetime.now(UTC))

    assert q.position("u1") is None


def test_queue_has_user_in_waiting():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")

    assert q.has_user("u1") is True
    assert q.has_user("u2") is False


def test_queue_has_user_being_served():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")

    q.call_next(datetime.now(UTC))

    assert q.has_user("u1") is True


def test_queue_total_length_counts_serving():
    q = Queue(label="A", room_id="R1")
    q.enqueue("u1")
    q.enqueue("u2")

    q.call_next(datetime.now(UTC))

    assert q.total_length() == 2


# ---------------------------------------------------------------------------
# Queue.split_off_half / absorb (политика ребалансировки)
# ---------------------------------------------------------------------------


def _q_with(label: str, n: int) -> Queue:
    q = Queue(label=label, room_id="R1")
    for i in range(n):
        q.enqueue(f"u{i}")
    return q


def test_split_off_half_empty_queue_moves_nothing():
    q = _q_with("A", 0)
    assert q.split_off_half() == []
    assert len(q.waiting) == 0


def test_split_off_half_single_waiting_moves_nothing():
    # Регрессия: единственный ожидающий НЕ должен переноситься (1 // 2 == 0).
    q = _q_with("A", 1)
    moved = q.split_off_half()
    assert moved == []
    assert len(q.waiting) == 1


def test_split_off_half_even_splits_evenly():
    q = _q_with("A", 4)
    moved = q.split_off_half()
    assert len(moved) == 2
    assert len(q.waiting) == 2


def test_split_off_half_odd_keeps_majority_in_source():
    q = _q_with("A", 5)
    moved = q.split_off_half()
    assert len(moved) == 2
    assert len(q.waiting) == 3


def test_split_off_half_takes_from_tail():
    q = _q_with("A", 4)  # u0,u1,u2,u3
    moved = q.split_off_half()
    assert [t.user_id for t in moved] == ["u2", "u3"]
    assert [t.user_id for t in q.waiting] == ["u0", "u1"]


def test_absorb_relabels_and_counts():
    src = _q_with("A", 2)
    dst = Queue(label="B", room_id="R1")
    moved = src.waiting[:]
    dst.absorb(moved)
    assert len(dst.waiting) == 2
    assert dst.ticket_counter == 2
    for t in dst.waiting:
        assert t.queue_label == "B"


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


def test_room_can_add_queue_below_max():
    r = Room(room_id="R1", owner_id="u1", queue_labels=["A"])

    assert r.can_add_queue() is True


def test_room_cannot_add_queue_at_max():
    r = Room(room_id="R1", owner_id="u1", queue_labels=list(QUEUE_LABELS[:MAX_QUEUES]))

    assert r.can_add_queue() is False


def test_room_next_queue_label_skips_existing():
    r = Room(room_id="R1", owner_id="u1", queue_labels=["A", "B"])

    assert r.next_queue_label() == "C"


def test_room_next_queue_label_raises_when_full():
    r = Room(room_id="R1", owner_id="u1", queue_labels=list(QUEUE_LABELS))

    with pytest.raises(ValueError):
        r.next_queue_label()


def test_room_can_remove_queue_when_multiple():
    r = Room(room_id="R1", owner_id="u1", queue_labels=["A", "B"])

    assert r.can_remove_queue("A") is True


def test_room_cannot_remove_last_queue():
    r = Room(room_id="R1", owner_id="u1", queue_labels=["A"])

    assert r.can_remove_queue("A") is False


def test_room_cannot_remove_nonexistent_queue():
    r = Room(room_id="R1", owner_id="u1", queue_labels=["A", "B"])

    assert r.can_remove_queue("C") is False


def test_room_is_closed():
    r = Room(room_id="R1", owner_id="u1", closed=True)

    assert r.is_closed() is True


def test_room_default_queue_label_is_first():
    assert QUEUE_LABELS[0] == DEFAULT_QUEUE


def test_queue_labels_no_i():
    assert "I" not in QUEUE_LABELS


def test_queue_labels_has_k():
    assert "K" in QUEUE_LABELS
