from functools import lru_cache
from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Rizg Liquidity Tracker"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    quote_history_limit: int = Field(default=1000, ge=10, le=100_000)
    ws_heartbeat_seconds: int = Field(default=20, ge=5, le=120)
    enable_mock_feed: bool = True
    mock_feed_interval_seconds: float = Field(default=0.5, ge=0.05, le=30)
    mock_feed_symbols: list[str] = Field(
        default_factory=lambda: ["AAPL", "MSFT", "TSLA", "NVDA", "4030"]
    )
    sahmk_api_key: str = ""
    sahmk_rest_url: str = "https://api.sahmk.sa/api/v1"
    sahmk_data_mode: str = "delayed"
    sahmk_poll_seconds: float = Field(default=30, ge=5, le=600)
    sahmk_symbols: list[str] = Field(default_factory=lambda: ["4030"])
    screener_leader_limit: int = Field(default=10, ge=3, le=25)
    signal_net_flow_threshold: Decimal = Field(default=Decimal("15000"))
    signal_aggressive_ratio: Decimal = Field(default=Decimal("0.58"))
    signal_atr_target_mult: Decimal = Field(default=Decimal("1.5"))
    signal_atr_stop_mult: Decimal = Field(default=Decimal("1.0"))
    telegram_enabled: bool = False
    alert_window_seconds: int = Field(default=60, ge=5, le=600)
    alert_inflow_threshold: Decimal = Field(default=Decimal("25000"))
    alert_volume_threshold: Decimal = Field(default=Decimal("8000"))
    alert_net_flow_threshold: Decimal = Field(default=Decimal("15000"))
    alert_cooldown_seconds: int = Field(default=20, ge=0, le=3600)
    alert_history_limit: int = Field(default=50, ge=5, le=500)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_report_interval_minutes: int = Field(default=30, ge=1, le=1440)
    telegram_report_symbols: list[str] = Field(default_factory=lambda: ["4030"])

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
