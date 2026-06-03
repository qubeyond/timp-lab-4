from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Заведомо небезопасные значения секрета, которые недопустимы на проде.
_WEAK_JWT_SECRETS = {
    "dev-secret-change-in-prod",
    "change_me_to_a_random_64_char_string",
    "secret",
    "changeme",
}
_MIN_JWT_SECRET_LEN = 32  # байт, рекомендация RFC 7518 для HS256


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    # database
    postgres_user: str = Field("queue", alias="POSTGRES_USER")
    postgres_password: str = Field("queue", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field("queue", alias="POSTGRES_DB")
    postgres_host: str = Field("postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")

    # redis
    redis_host: str = Field("redis", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    queue_ttl: int = Field(86400, alias="QUEUE_TTL")

    # auth
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(1440, alias="JWT_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # app
    debug: bool = Field(False, alias="DEBUG")
    cors_origins_raw: str = Field("*", alias="CORS_ORIGINS")

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> Settings:
        # В проде (DEBUG=false) запрещаем дефолтные/короткие секреты —
        # иначе любой, кто знает плейсхолдер, подделает админ-токен.
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
