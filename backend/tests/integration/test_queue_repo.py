from datetime import UTC, datetime

import pytest

from src.domain.entities import Queue

pytestmark = pytest.mark.integration

ROOM = "TESTROOM"


# ---------------------------------------------------------------------------
# room / owner
# ---------------------------------------------------------------------------


async def test_room_not_exists_initially(queue_repo):
    assert await queue_repo.room_exists(ROOM) is False


async def test_set_owner_makes_room_exist(queue_repo):
    await queue_repo.set_owner(ROOM, "fp123")
    assert await queue_repo.room_exists(ROOM) is True
    assert await queue_repo.get_owner(ROOM) == "fp123"


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------


async def test_save_and_load_waiting(queue_repo):
    q = Queue(label="A", room_id=ROOM)
    q.enqueue("u1")
    q.enqueue("u2")
    await queue_repo.save(q)

    loaded = await queue_repo.load(ROOM, "A")
    assert loaded is not None
    assert [t.user_id for t in loaded.waiting] == ["u1", "u2"]
    assert [t.num for t in loaded.waiting] == ["A1", "A2"]
    assert loaded.ticket_counter == 2


async def test_load_missing_queue_returns_none(queue_repo):
    assert await queue_repo.load(ROOM, "Z") is None


async def test_save_preserves_serving_and_started_at(queue_repo):
    q = Queue(label="A", room_id=ROOM)
    q.enqueue("u1")
    started = datetime.now(UTC)
    q.call_next(started)
    await queue_repo.save(q)

    loaded = await queue_repo.load(ROOM, "A")
    assert loaded.serving is not None
    assert loaded.serving.user_id == "u1"
    assert loaded.serving_since is not None
    # Регрессия started_at: время старта обслуживания должно сохраняться (±1с).
    assert abs((loaded.serving_since - started).total_seconds()) < 1


async def test_resave_serving_without_serving_since_keeps_started_at(queue_repo):
    """Регрессия: повторное сохранение serving-очереди не должно обнулять started_at."""
    q = Queue(label="A", room_id=ROOM)
    q.enqueue("u1")
    started = datetime.now(UTC)
    q.call_next(started)
    await queue_repo.save(q)

    # Эмулируем объект, у которого serving есть, а serving_since утрачен.
    q2 = await queue_repo.load(ROOM, "A")
    q2.serving_since = None
    await queue_repo.save(q2)

    reloaded = await queue_repo.load(ROOM, "A")
    assert reloaded.serving is not None
    assert reloaded.serving_since is not None
    assert abs((reloaded.serving_since - started).total_seconds()) < 1


async def test_load_all_sorted(queue_repo):
    await queue_repo.save(Queue(label="B", room_id=ROOM))
    await queue_repo.save(Queue(label="A", room_id=ROOM))
    queues = await queue_repo.load_all(ROOM)
    assert [q.label for q in queues] == ["A", "B"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_removes_queue(queue_repo):
    await queue_repo.save(Queue(label="A", room_id=ROOM))
    await queue_repo.save(Queue(label="B", room_id=ROOM))
    await queue_repo.delete(ROOM, "B")
    labels = [q.label for q in await queue_repo.load_all(ROOM)]
    assert labels == ["A"]


async def test_delete_all_cleans_room(queue_repo):
    await queue_repo.set_owner(ROOM, "fp")
    q = Queue(label="A", room_id=ROOM)
    q.enqueue("u1")
    await queue_repo.save(q)

    await queue_repo.delete_all(ROOM)

    assert await queue_repo.room_exists(ROOM) is False
    assert await queue_repo.get_owner(ROOM) is None
    assert await queue_repo.load_all(ROOM) == []


# ---------------------------------------------------------------------------
# avg serve (атомарный Lua)
# ---------------------------------------------------------------------------


async def test_update_avg_serve_first_value(queue_repo):
    await queue_repo.update_avg_serve(ROOM, 100)
    assert await queue_repo.get_avg_serve(ROOM) == 100


async def test_update_avg_serve_cumulative_average(queue_repo):
    await queue_repo.update_avg_serve(ROOM, 100)
    await queue_repo.update_avg_serve(ROOM, 200)
    # Кумулятивное среднее: 100, затем 100 + (200-100)/2 = 150.
    assert await queue_repo.get_avg_serve(ROOM) == 150


async def test_get_avg_serve_none_when_unset(queue_repo):
    assert await queue_repo.get_avg_serve(ROOM) is None


# ---------------------------------------------------------------------------
# TTL
# ---------------------------------------------------------------------------


async def test_save_sets_ttl(queue_repo, redis_client):
    from src.infrastructure.redis.client import queue_current_key, queue_list_key

    q = Queue(label="A", room_id=ROOM)
    q.enqueue("u1")
    await queue_repo.save(q)

    for key in (queue_list_key(ROOM, "A"), queue_current_key(ROOM, "A")):
        ttl = await redis_client.ttl(key)
        assert ttl > 0, f"{key} has no TTL"
