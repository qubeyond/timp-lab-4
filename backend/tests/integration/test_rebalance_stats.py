import pytest

from src.domain.constants import DEFAULT_QUEUE
from src.domain.entities import Queue

pytestmark = pytest.mark.integration

ROOM = "REBTEST"
OWNER = "owner_fp"


async def _open_room(queue_repo) -> None:
    """Создаёт комнату напрямую через репозиторий (детерминированный ID)."""
    await queue_repo.set_owner(ROOM, OWNER)
    await queue_repo.save(Queue(label=DEFAULT_QUEUE, room_id=ROOM))


async def _take(visitor_service, user_id: str, hint=None):
    return await visitor_service.take_ticket(ROOM, hint, user_id)


async def _lengths(queue_repo) -> dict[str, int]:
    return {q.label: len(q.waiting) for q in await queue_repo.load_all(ROOM)}


# ---------------------------------------------------------------------------
# add_queue rebalance — регрессия основного бага
# ---------------------------------------------------------------------------


async def test_add_queue_with_single_waiting_does_not_empty_source(
    queue_repo, room_service, visitor_service
):
    """Главная регрессия: 1 человек в A, админ создаёт B — человек ОСТАЁТСЯ в A."""
    await _open_room(queue_repo)
    await _take(visitor_service, "lonely_user")

    await room_service.add_queue(ROOM, OWNER)

    lengths = await _lengths(queue_repo)
    assert lengths == {"A": 1, "B": 0}, f"человека выкинуло из A: {lengths}"

    # И он реально в A с корректной меткой.
    a = await queue_repo.load(ROOM, "A")
    assert a.waiting[0].user_id == "lonely_user"
    assert a.waiting[0].queue_label == "A"


async def test_add_queue_even_split(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    for i in range(4):
        await _take(visitor_service, f"u{i}", hint="A")

    await room_service.add_queue(ROOM, OWNER)

    lengths = await _lengths(queue_repo)
    assert lengths == {"A": 2, "B": 2}


async def test_add_queue_odd_keeps_majority_in_source(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    for i in range(5):
        await _take(visitor_service, f"u{i}", hint="A")

    await room_service.add_queue(ROOM, OWNER)

    lengths = await _lengths(queue_repo)
    assert lengths == {"A": 3, "B": 2}


async def test_moved_tickets_keep_their_num_but_change_label(
    queue_repo, room_service, visitor_service
):
    await _open_room(queue_repo)
    for i in range(4):
        await _take(visitor_service, f"u{i}", hint="A")

    await room_service.add_queue(ROOM, OWNER)

    b = await queue_repo.load(ROOM, "B")
    for t in b.waiting:
        assert t.queue_label == "B"
        # Номер талона исторический (A3/A4) — он же используется в БД-истории.
        assert t.num.startswith("A")


# ---------------------------------------------------------------------------
# remove_queue redistribute
# ---------------------------------------------------------------------------


async def test_remove_queue_redistributes_to_remaining(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    await room_service.add_queue(ROOM, OWNER)  # B
    for i in range(3):
        await _take(visitor_service, f"u{i}", hint="B")

    await room_service.remove_queue(ROOM, "B", OWNER)

    labels = [q.label for q in await queue_repo.load_all(ROOM)]
    assert "B" not in labels
    a = await queue_repo.load(ROOM, "A")
    assert len(a.waiting) == 3
    for t in a.waiting:
        assert t.queue_label == "A"


# ---------------------------------------------------------------------------
# stats + avg serve (раньше среднее никогда не считалось)
# ---------------------------------------------------------------------------


async def test_full_cycle_updates_stats_and_avg(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    for i in range(3):
        await _take(visitor_service, f"u{i}", hint="A")

    for _ in range(3):
        await room_service.call_next(ROOM, "A", OWNER)
        await room_service.complete_serving(ROOM, "A", OWNER)

    stats = await room_service.get_stats(ROOM)
    assert stats["total_tickets"] == 3
    assert stats["completed"] == 3

    # Среднее время обслуживания теперь действительно пишется в Redis.
    avg = await queue_repo.get_avg_serve(ROOM)
    assert avg is not None
    assert avg >= 0


# ---------------------------------------------------------------------------
# owner check
# ---------------------------------------------------------------------------


async def test_admin_mutation_rejects_wrong_owner(queue_repo, room_service):
    from fastapi import HTTPException

    await _open_room(queue_repo)
    with pytest.raises(HTTPException) as exc:
        await room_service.add_queue(ROOM, "not_the_owner")
    assert exc.value.status_code == 403
