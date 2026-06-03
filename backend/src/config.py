from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_JWT_SECRETS = {
    "dev-secret-change-in-prod",
    "change_me_to_a_random_64_char_string",
    "secret",
    "changeme",
}
_MIN_JWT_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    postgres_user: str = Field("queue", alias="POSTGRES_USER")
    postgres_password: str = Field("queue", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field("queue", alias="POSTGRES_DB")
    postgres_host: str = Field("postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")

    redis_host: str = Field("redis", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    queue_ttl: int = Field(86400, alias="QUEUE_TTL")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(60, alias="JWT_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    invite_ttl_seconds: int = Field(3600, alias="INVITE_TTL_SECONDS")
    queue_code_length: int = Field(4, alias="QUEUE_CODE_LENGTH")
    ws_max_connections_per_user: int = Field(5, alias="WS_MAX_CONNECTIONS_PER_USER")
    room_lock_timeout: float = Field(5.0, alias="ROOM_LOCK_TIMEOUT")
    max_invites_per_room: int = Field(20, alias="MAX_INVITES_PER_ROOM")

    rate_limit_queue: str = Field("30/minute", alias="RATE_LIMIT_QUEUE")
    rate_limit_admin: str = Field("60/minute", alias="RATE_LIMIT_ADMIN")
    rate_limit_auth: str = Field("30/minute", alias="RATE_LIMIT_AUTH")
    rate_limit_feedback: str = Field("5/minute", alias="RATE_LIMIT_FEEDBACK")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_format: str = Field("%(asctime)s [%(levelname)s] %(name)s: %(message)s", alias="LOG_FORMAT")
    telegram_timeout: float = Field(10.0, alias="TELEGRAM_TIMEOUT")

    debug: bool = Field(False, alias="DEBUG")
    cors_origins_raw: str = Field("*", alias="CORS_ORIGINS")

    telegram_bot_token: str = Field("", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field("", alias="TELEGRAM_CHAT_ID")

    app_version: str = Field("v.test", alias="APP_VERSION")

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> Settings:
        if not self.debug:
            if self.jwt_secret in _WEAK_JWT_SECRETS:
                raise ValueError(
                    "JWT_SECRET содержит небезопасное значение по умолчанию. "
                    "Задайте случайный секрет (например, `openssl rand -hex 32`)."
                )
            if len(self.jwt_secret.encode("utf-8")) < _MIN_JWT_SECRET_LEN:
                raise ValueError(
                    f"JWT_SECRET слишком короткий: нужно не менее {_MIN_JWT_SECRET_LEN} "
                    "байт для HS256."
                )
        return self

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]


settings = Settings()
