import asyncio

import pytest

from src.domain.constants import DEFAULT_QUEUE
from src.domain.entities import Queue

pytestmark = pytest.mark.integration

ROOM = "LOADTEST"
OWNER = "owner_fp"


async def _open_room(queue_repo) -> None:
    await queue_repo.set_owner(ROOM, OWNER)
    await queue_repo.save(Queue(label=DEFAULT_QUEUE, room_id=ROOM))


async def _total_waiting(queue_repo) -> int:
    return sum(len(q.waiting) for q in await queue_repo.load_all(ROOM))


# ---------------------------------------------------------------------------
# concurrent take_ticket
# ---------------------------------------------------------------------------


async def test_concurrent_take_ticket_all_enqueued(queue_repo, visitor_service):
    await _open_room(queue_repo)
    users = [f"user_{i:03d}" for i in range(30)]

    await asyncio.gather(*[visitor_service.take_ticket(ROOM, "A", u) for u in users])

    a = await queue_repo.load(ROOM, "A")
    enqueued = {t.user_id for t in a.waiting}
    # Каждый пользователь должен оказаться в очереди ровно один раз.
    assert enqueued == set(users), f"потеряны/задвоены пользователи: {len(enqueued)} из 30"


async def test_concurrent_take_ticket_balances_across_queues(queue_repo, visitor_service):
    await _open_room(queue_repo)
    # Три очереди.
    await queue_repo.save(Queue(label="B", room_id=ROOM))
    await queue_repo.save(Queue(label="C", room_id=ROOM))

    users = [f"u_{i:03d}" for i in range(30)]
    await asyncio.gather(*[visitor_service.take_ticket(ROOM, None, u) for u in users])

    assert await _total_waiting(queue_repo) == 30


# ---------------------------------------------------------------------------
# concurrent call_next (только один забирает талон)
# ---------------------------------------------------------------------------


async def test_concurrent_call_next_serves_each_ticket_once(
    queue_repo, room_service, visitor_service
):
    await _open_room(queue_repo)
    for i in range(5):
        await visitor_service.take_ticket(ROOM, "A", f"u_{i}")

    # Пять параллельных call_next на очередь из 5 — каждый талон вызван не более раза.
    results = await asyncio.gather(
        *[room_service.call_next(ROOM, "A", OWNER) for _ in range(5)],
        return_exceptions=True,
    )
    served = [r.ticket for r in results if not isinstance(r, Exception)]
    assert len(served) == len(set(served)), f"один талон вызван дважды: {served}"


# ---------------------------------------------------------------------------
# avg serve атомарность
# ---------------------------------------------------------------------------


async def test_concurrent_update_avg_serve_counts_all(queue_repo):
    # 20 параллельных обновлений среднего — счётчик не должен потеряться.
    await asyncio.gather(*[queue_repo.update_avg_serve(ROOM, 100) for _ in range(20)])

    from src.infrastructure.redis.client import room_serve_count_key

    count = await queue_repo._r.get(room_serve_count_key(ROOM))
    assert int(count) == 20, f"гонка в счётчике среднего: {count}"
    # Все значения одинаковые -> среднее ровно 100.
    assert await queue_repo.get_avg_serve(ROOM) == 100


# ---------------------------------------------------------------------------
# sequential high load
# ---------------------------------------------------------------------------


async def test_high_load_call_complete_cycle_empties_queue(
    queue_repo, room_service, visitor_service
):
    await _open_room(queue_repo)
    n = 50
    for i in range(n):
        await visitor_service.take_ticket(ROOM, "A", f"u_{i}")

    for _ in range(n):
        await room_service.call_next(ROOM, "A", OWNER)
        await room_service.complete_serving(ROOM, "A", OWNER)

    a = await queue_repo.load(ROOM, "A")
    assert len(a.waiting) == 0
    assert a.serving is None


# ---------------------------------------------------------------------------
# rebalance during concurrent joins
# ---------------------------------------------------------------------------


async def test_rebalance_during_concurrent_joins_keeps_all(
    queue_repo, room_service, visitor_service
):
    await _open_room(queue_repo)
    for i in range(20):
        await visitor_service.take_ticket(ROOM, "A", f"pre_{i}")

    async def joiners():
        await asyncio.gather(
            *[visitor_service.take_ticket(ROOM, None, f"late_{i}") for i in range(10)]
        )

    await asyncio.gather(room_service.add_queue(ROOM, OWNER), joiners())

    total = await _total_waiting(queue_repo)
    assert total == 30, f"ожидалось 30, получено {total}"
