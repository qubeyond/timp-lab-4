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
    return f"room:{room_id}:queue:{label}:status"


def queue_code_key(room_id: str, label: str) -> str:
    return f"room:{room_id}:queue:{label}:code"


def room_codes_key(room_id: str) -> str:
    return f"room:{room_id}:codes"


def room_flags_key(room_id: str) -> str:
    return f"room:{room_id}:flags"


def room_queues_key(room_id: str) -> str:
    return f"room:{room_id}:queues"


def room_owner_key(room_id: str) -> str:
    return f"room:{room_id}:owner"


def room_admins_key(room_id: str) -> str:
    return f"room:{room_id}:admins"


def room_invite_key(room_id: str, token: str) -> str:
    return f"room:{room_id}:invite:{token}"


def room_invites_set_key(room_id: str) -> str:
    return f"room:{room_id}:invites"


def revoked_token_key(jti: str) -> str:
    return f"revoked:{jti}"


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
