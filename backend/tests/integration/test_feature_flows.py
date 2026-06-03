"""Интеграционные тесты новых фич против реального Redis."""

import pytest
from fastapi import HTTPException

from src.domain.entities import DEFAULT_QUEUE, TICKET_ON_WAY, Queue
from src.infrastructure.redis.queue_repo import generate_queue_code

pytestmark = pytest.mark.integration

ROOM = "FEATRM"
OWNER = "owner_fp"


async def _open_room(queue_repo, *, is_open=True, balancer=True, code="CODE"):
    await queue_repo.set_owner(ROOM, OWNER)
    await queue_repo.set_room_flags(ROOM, is_open=is_open, balancer_enabled=balancer)
    await queue_repo.save(Queue(label=DEFAULT_QUEUE, room_id=ROOM, code=code))


# ---------------------------------------------------------------------------
# Флаги комнаты round-trip
# ---------------------------------------------------------------------------


async def test_room_flags_persist(queue_repo):
    await queue_repo.set_room_flags(ROOM, is_open=False, balancer_enabled=False)
    flags = await queue_repo.get_room_flags(ROOM)
    assert flags == {"is_open": False, "balancer_enabled": False}


async def test_room_flags_default_open(queue_repo):
    # Без явной установки — считаем открытой и с балансировщиком.
    flags = await queue_repo.get_room_flags("NEVERSET")
    assert flags == {"is_open": True, "balancer_enabled": True}


async def test_partial_flag_update(queue_repo):
    await queue_repo.set_room_flags(ROOM, is_open=True, balancer_enabled=True)
    await queue_repo.set_room_flags(ROOM, is_open=False)  # только один флаг
    flags = await queue_repo.get_room_flags(ROOM)
    assert flags == {"is_open": False, "balancer_enabled": True}


# ---------------------------------------------------------------------------
# Код очереди и обратный индекс
# ---------------------------------------------------------------------------


async def test_queue_code_round_trip(queue_repo):
    await queue_repo.save(Queue(label="A", room_id=ROOM, code="X7K2"))
    loaded = await queue_repo.load(ROOM, "A")
    assert loaded.code == "X7K2"


async def test_find_label_by_code(queue_repo):
    await queue_repo.save(Queue(label="A", room_id=ROOM, code="AAAA"))
    await queue_repo.save(Queue(label="B", room_id=ROOM, code="BBBB"))
    assert await queue_repo.find_label_by_code(ROOM, "BBBB") == "B"
    assert await queue_repo.find_label_by_code(ROOM, "ZZZZ") is None


async def test_delete_queue_removes_code_index(queue_repo):
    await queue_repo.save(Queue(label="A", room_id=ROOM, code="AAAA"))
    await queue_repo.save(Queue(label="B", room_id=ROOM, code="BBBB"))
    await queue_repo.delete(ROOM, "B")
    assert await queue_repo.find_label_by_code(ROOM, "BBBB") is None


# ---------------------------------------------------------------------------
# Статус талона round-trip
# ---------------------------------------------------------------------------


async def test_ticket_status_persists(queue_repo):
    q = Queue(label="A", room_id=ROOM)
    q.enqueue("u1")
    q.set_status("u1", TICKET_ON_WAY)
    await queue_repo.save(q)

    loaded = await queue_repo.load(ROOM, "A")
    assert loaded.waiting[0].status == TICKET_ON_WAY


# ---------------------------------------------------------------------------
# Сервисный слой: вход по коду / закрытый приём / балансировщик off
# ---------------------------------------------------------------------------


async def test_closed_room_rejects_new_ticket(queue_repo, visitor_service):
    await _open_room(queue_repo, is_open=False)
    with pytest.raises(HTTPException) as exc:
        await visitor_service.take_ticket(ROOM, None, "newbie")
    assert exc.value.status_code == 403


async def test_balancer_off_join_by_code(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo, balancer=False, code="AAAA")
    await room_service.add_queue(ROOM, OWNER)  # B с собственным кодом
    b = await queue_repo.load(ROOM, "B")

    res = await visitor_service.take_ticket(ROOM, None, "vip", queue_code=b.code)
    assert res.queue_label == "B"


async def test_balancer_off_without_code_routes_to_random_queue(queue_repo, visitor_service):
    # VIP-режим, общая ссылка без кода → случайная очередь, а не отказ.
    await _open_room(queue_repo, balancer=False, code="AAAA")
    await queue_repo.save(Queue(label="B", room_id=ROOM, code="BBBB"))
    res = await visitor_service.take_ticket(ROOM, None, "guest")
    assert res.queue_label in {"A", "B"}
    assert res.ticket is not None


# ---------------------------------------------------------------------------
# Пропуск не засчитывается в статистику (feature 8)
# ---------------------------------------------------------------------------


async def test_skip_does_not_count_in_avg(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    await visitor_service.take_ticket(ROOM, "A", "u1")
    await room_service.call_next(ROOM, "A", OWNER)
    await room_service.skip_serving(ROOM, "A", OWNER)

    # Среднее время обслуживания не должно появиться (никого не обслужили).
    assert await queue_repo.get_avg_serve(ROOM) is None
    a = await queue_repo.load(ROOM, "A")
    assert a.serving is None


# ---------------------------------------------------------------------------
# Перемещение талона между очередями (feature 5)
# ---------------------------------------------------------------------------


async def test_move_ticket_between_queues_persists(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    await room_service.add_queue(ROOM, OWNER)  # B
    await visitor_service.take_ticket(ROOM, "A", "u1")  # талон A1

    await room_service.move_ticket(ROOM, OWNER, "A1", "B", 0)

    a = await queue_repo.load(ROOM, "A")
    b = await queue_repo.load(ROOM, "B")
    assert all(t.user_id != "u1" for t in a.waiting)
    assert b.waiting[0].user_id == "u1"
    assert b.waiting[0].queue_label == "B"


async def test_move_ticket_reorder_within_queue(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    for i in range(3):
        await visitor_service.take_ticket(ROOM, "A", f"u{i}")  # A1, A2, A3

    await room_service.move_ticket(ROOM, OWNER, "A3", "A", 0)

    a = await queue_repo.load(ROOM, "A")
    assert a.waiting[0].user_id == "u2"  # u2 взял A3, теперь первый


# ---------------------------------------------------------------------------
# Статус через сервис (feature 9)
# ---------------------------------------------------------------------------


async def test_set_status_round_trip(queue_repo, visitor_service):
    await _open_room(queue_repo)
    await visitor_service.take_ticket(ROOM, "A", "u1")

    await visitor_service.set_status(ROOM, "u1", "on_way")

    a = await queue_repo.load(ROOM, "A")
    assert a.waiting[0].status == "on_way"


async def test_enabling_balancer_rebalances_existing(queue_repo, room_service, visitor_service):
    """Регрессия: включение балансировщика раскидывает уже стоящих по очередям."""
    await _open_room(queue_repo, balancer=False, code="AAAA")
    await room_service.add_queue(ROOM, OWNER)  # B

    # Все 6 человек встают в A (балансировщик off → вход по метке).
    for i in range(6):
        await visitor_service.take_ticket(ROOM, "A", f"u{i}")

    a_before = await queue_repo.load(ROOM, "A")
    b_before = await queue_repo.load(ROOM, "B")
    assert len(a_before.waiting) == 6
    assert len(b_before.waiting) == 0

    # Включаем балансировщик — должно выровнять (round-robin 6 -> 3/3).
    await room_service.set_balancer(ROOM, OWNER, True)

    a = await queue_repo.load(ROOM, "A")
    b = await queue_repo.load(ROOM, "B")
    assert len(a.waiting) == 3
    assert len(b.waiting) == 3
    # Метки талонов в B обновлены.
    assert all(t.queue_label == "B" for t in b.waiting)


async def test_disabling_balancer_does_not_rebalance(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo, balancer=True, code="AAAA")
    await room_service.add_queue(ROOM, OWNER)
    for i in range(4):
        await visitor_service.take_ticket(ROOM, "A", f"u{i}")

    before = {q.label: len(q.waiting) for q in await queue_repo.load_all(ROOM)}
    await room_service.set_balancer(ROOM, OWNER, False)
    after = {q.label: len(q.waiting) for q in await queue_repo.load_all(ROOM)}
    assert before == after  # выключение ничего не двигает


async def test_serving_status_round_trip(queue_repo, room_service, visitor_service):
    """Статус «не приду» у вызванного талона сохраняется и виден в стейте."""
    await _open_room(queue_repo)
    await visitor_service.take_ticket(ROOM, "A", "u1")
    await room_service.call_next(ROOM, "A", OWNER)  # u1 теперь serving

    await visitor_service.set_status(ROOM, "u1", "no_show")

    q = await queue_repo.load(ROOM, "A")
    assert q.serving is not None
    assert q.serving.status == "no_show"


async def test_unique_codes_on_add_queue(queue_repo, room_service):
    await _open_room(queue_repo, code="AAAA")
    await room_service.add_queue(ROOM, OWNER)
    await room_service.add_queue(ROOM, OWNER)
    queues = await queue_repo.load_all(ROOM)
    codes = [q.code for q in queues if q.code]
    assert len(codes) == len(set(codes)), "коды очередей должны быть уникальны"


def test_generate_queue_code_format():
    code = generate_queue_code()
    assert len(code) == 4
    assert code.isalnum()


# ---------------------------------------------------------------------------
# Со-администраторы (приглашение)
# ---------------------------------------------------------------------------


async def test_invite_flow_makes_co_admin(queue_repo, room_service):
    await _open_room(queue_repo)
    # Изначально посторонний — не админ.
    assert await queue_repo.is_admin(ROOM, "helper") is False

    invite = await room_service.create_invite(ROOM, OWNER)
    accepted = await room_service.accept_invite(ROOM, invite["token"], "helper")

    assert accepted["room_id"] == ROOM
    assert await queue_repo.is_admin(ROOM, "helper") is True


async def test_invite_is_single_use(queue_repo, room_service):
    await _open_room(queue_repo)
    invite = await room_service.create_invite(ROOM, OWNER)
    await room_service.accept_invite(ROOM, invite["token"], "helper1")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await room_service.accept_invite(ROOM, invite["token"], "helper2")
    assert exc.value.status_code == 400


async def test_co_admin_can_mutate_owner_keeps_close(queue_repo, room_service, visitor_service):
    await _open_room(queue_repo)
    invite = await room_service.create_invite(ROOM, OWNER)
    await room_service.accept_invite(ROOM, invite["token"], "helper")
    await visitor_service.take_ticket(ROOM, "A", "u1")

    # Со-админ может вызывать следующего.
    await room_service.call_next(ROOM, "A", "helper")
    q = await queue_repo.load(ROOM, "A")
    assert q.serving is not None

    # Но закрыть комнату со-админ не может — только владелец.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await room_service.close_room(ROOM, "helper")
    assert exc.value.status_code == 403


async def test_non_owner_cannot_invite(queue_repo, room_service):
    await _open_room(queue_repo)
    invite = await room_service.create_invite(ROOM, OWNER)
    await room_service.accept_invite(ROOM, invite["token"], "helper")

    from fastapi import HTTPException

    # Со-админ (helper) не владелец → не может раздавать приглашения.
    with pytest.raises(HTTPException) as exc:
        await room_service.create_invite(ROOM, "helper")
    assert exc.value.status_code == 403


async def test_accept_invite_idempotent(queue_repo, room_service):
    """Повторный приём приглашения тем же пользователем не падает (StrictMode/реклик)."""
    await _open_room(queue_repo)
    invite = await room_service.create_invite(ROOM, OWNER)
    await room_service.accept_invite(ROOM, invite["token"], "helper")

    # Тот же токен уже погашен, но helper уже админ → второй раз ОК.
    again = await room_service.accept_invite(ROOM, invite["token"], "helper")
    assert again["room_id"] == ROOM
    assert await queue_repo.is_admin(ROOM, "helper") is True


async def test_co_admin_leave_drops_rights(queue_repo, room_service):
    await _open_room(queue_repo)
    invite = await room_service.create_invite(ROOM, OWNER)
    await room_service.accept_invite(ROOM, invite["token"], "helper")
    assert await queue_repo.is_admin(ROOM, "helper") is True

    await room_service.leave_admin(ROOM, "helper")
    assert await queue_repo.is_admin(ROOM, "helper") is False


async def test_owner_cannot_leave(queue_repo, room_service):
    await _open_room(queue_repo)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await room_service.leave_admin(ROOM, OWNER)
    assert exc.value.status_code == 400


async def test_resume_admin_no_ticket_created(queue_repo, room_service):
    """Восстановление админ-сессии не создаёт талон и переоформляет токен."""
    await _open_room(queue_repo)
    invite = await room_service.create_invite(ROOM, OWNER)
    await room_service.accept_invite(ROOM, invite["token"], "helper")

    res = await room_service.resume_admin(ROOM, "helper")
    assert res["access_token"]
    assert res["is_owner"] is False

    # Главное: никаких талонов не появилось.
    total = sum(len(q.waiting) for q in await queue_repo.load_all(ROOM))
    assert total == 0


async def test_resume_owner_flag(queue_repo, room_service):
    await _open_room(queue_repo)
    res = await room_service.resume_admin(ROOM, OWNER)
    assert res["is_owner"] is True


async def test_resume_rejects_non_admin(queue_repo, room_service):
    await _open_room(queue_repo)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await room_service.resume_admin(ROOM, "stranger")
    assert exc.value.status_code == 403


async def test_vip_no_code_routes_to_a_queue(queue_repo, room_service, visitor_service):
    """VIP (balancer off): вход по общей ссылке без кода → попадает в одну из очередей."""
    await _open_room(queue_repo, balancer=False, code="AAAA")
    await room_service.add_queue(ROOM, OWNER)  # B

    res = await visitor_service.take_ticket(ROOM, None, "guest")
    assert res.queue_label in {"A", "B"}
    assert res.ticket is not None
