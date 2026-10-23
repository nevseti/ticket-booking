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

    # Бронирование
    hold_ttl_seconds: int = 10 * 60  # сколько живёт удержание места
    max_holds_per_event: int = 6  # сколько мест один пользователь держит на мероприятие

    # Банк-имитатор (оплата в MVP ненастоящая)
    fake_payment_latency_ms: int = 600  # «время ответа банка»
    fake_payment_decline_rate: float = 0.0  # доля случайных отказов (для нагрузочного теста)

    # Почта (в разработке и на демо — Mailpit: письма никуда не уходят, видны в его веб-UI)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_from: str = "Билеты <tickets@nevseti.duckdns.org>"
    public_url: str = "http://127.0.0.1:5173"  # для ссылок в письмах

    # Фоновый воркер
    hold_sweep_interval_seconds: int = 15
    saga_recovery_interval_seconds: int = 60
    saga_stuck_after_seconds: int = 120

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
