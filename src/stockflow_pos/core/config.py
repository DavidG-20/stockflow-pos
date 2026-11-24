"""Application settings loaded from environment variables."""

from decimal import Decimal
import secrets

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration with ephemeral dev secret and production guardrails."""

    app_name: str = "StockFlow POS"
    app_env: str = "development"
    seed_demo_data: bool = True
    database_url: str = "sqlite:///./stockflow.db"
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    access_token_expire_minutes: int = 480
    igv_rate: Decimal = Decimal("0.18")
    expiry_alert_days: int = 30
    login_rate_limit_max: int = 10
    login_rate_limit_window_seconds: int = 60

    @model_validator(mode="after")
    def _validate_production_secret(self) -> "Settings":
        if self.app_env.lower() == "production" and len(self.secret_key.strip()) < 32:
            raise ValueError(
                "En producción (APP_ENV=production) SECRET_KEY debe tener al menos 32 caracteres."
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
