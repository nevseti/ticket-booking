from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "dev-only-secret-key-change-me-in-production-0123456789"


class Settings(BaseSettings):
    """Настройки приложения. Читаются из переменных окружения и файла .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "dev"

    database_url: str = "postgresql+asyncpg://tickets:tickets@localhost:5433/tickets"
    db_pool_size: int = 10
    db_max_overflow: int = 5

    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    secret_key: str = DEV_SECRET_KEY
    auth_cookie_name: str = "access_token"
    auth_token_ttl_minutes: int = 12 * 60

    log_level: str = "INFO"
    log_json: bool = False

    @model_validator(mode="after")
    def check_production_secrets(self) -> Self:
        if self.env == "prod" and (self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32):
            raise ValueError("На проде SECRET_KEY должен быть задан и не короче 32 символов")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
