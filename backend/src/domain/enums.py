from enum import IntEnum, StrEnum


class TicketStatus(StrEnum):
    WAITING = "waiting"
    ON_WAY = "on_way"
    NO_SHOW = "no_show"


class AdminRole(StrEnum):
    FULL = "full"
    QUEUES = "queues"


class Permission(StrEnum):
    QUEUES = "queues"
    SETTINGS = "settings"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"
    OWNER = "owner"


class QueueState(StrEnum):
    SERVING = "serving"
    WAITING = "waiting"


class WsMessageType(StrEnum):
    WELCOME = "welcome"
    UPDATE = "update"


class WsCloseCode(IntEnum):
    BAD_ROOM = 4400
    BAD_TOKEN = 4401
    FORBIDDEN = 4403
    TOO_MANY = 4429


ROLE_PERMISSIONS: dict[AdminRole, set[Permission]] = {
    AdminRole.FULL: {Permission.QUEUES, Permission.SETTINGS},
    AdminRole.QUEUES: {Permission.QUEUES},
}
