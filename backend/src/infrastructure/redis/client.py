import redis.asyncio as aioredis


def queue_list_key(room_id: str, label: str) -> str:
    return f"room:{room_id}:queue:{label}:list"


def queue_hash_key(room_id: str, label: str) -> str:
    return f"room:{room_id}:queue:{label}:identifiers"


def queue_current_key(room_id: str, label: str) -> str:
    return f"room:{room_id}:queue:{label}:current"


def queue_counter_key(room_id: str, label: str) -> str:
    return f"room:{room_id}:queue:{label}:counter"


def queue_status_key(room_id: str, label: str) -> str:
    # user_id -> статус ожидающего талона (waiting/on_way/no_show)
    return f"room:{room_id}:queue:{label}:status"


def queue_code_key(room_id: str, label: str) -> str:
    return f"room:{room_id}:queue:{label}:code"


def room_codes_key(room_id: str) -> str:
    # обратный индекс: code -> label, для входа по коду очереди
    return f"room:{room_id}:codes"


def room_flags_key(room_id: str) -> str:
    # is_open / balancer
    return f"room:{room_id}:flags"


def room_queues_key(room_id: str) -> str:
    return f"room:{room_id}:queues"


def room_owner_key(room_id: str) -> str:
    return f"room:{room_id}:owner"


def room_admins_key(room_id: str) -> str:
    # set из fingerprint-ов со-администраторов (без владельца)
    return f"room:{room_id}:admins"


def room_invite_key(room_id: str, token: str) -> str:
    return f"room:{room_id}:invite:{token}"


def user_queue_key(room_id: str) -> str:
    return f"room:{room_id}:user_queue"


def room_avg_serve_key(room_id: str) -> str:
    return f"room:{room_id}:avg_serve"


def room_serve_count_key(room_id: str) -> str:
    return f"room:{room_id}:serve_count"


def room_lock_key(room_id: str) -> str:
    return f"room:{room_id}:lock"


async def create_redis_client(url: str) -> aioredis.Redis:
    return aioredis.from_url(url, decode_responses=True)
