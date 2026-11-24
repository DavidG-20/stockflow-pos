"""Application settings loaded from environment variables."""

from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration with safe local defaults."""

    app_name: str = "StockFlow POS"
    database_url: str = "sqlite:///./stockflow.db"
    secret_key: str = "dev-secret-key-change-in-production-32chars"
    access_token_expire_minutes: int = 480
    igv_rate: Decimal = Decimal("0.18")
    expiry_alert_days: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
