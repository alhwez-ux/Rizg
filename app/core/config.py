from functools import lru_cache
from decimal import Decimal
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.is_file() else ".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = "Rizg Liquidity Tracker"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "*",
            "https://rizg.vercel.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    quote_history_limit: int = Field(default=1000, ge=10, le=100_000)
    ws_heartbeat_seconds: int = Field(default=20, ge=5, le=120)
    enable_mock_feed: bool = True
    mock_feed_interval_seconds: float = Field(default=0.5, ge=0.05, le=30)
    mock_feed_symbols: list[str] = Field(
        default_factory=lambda: ["AAPL", "MSFT", "TSLA", "NVDA", "4030"]
    )
    sahmk_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("SAHM_API_KEY", "SAHMK_API_KEY", "sahmk_api_key"),
    )
    sahmk_rest_url: str = Field(
        default="https://api.sahmk.sa/api/v1",
        validation_alias=AliasChoices("SAHM_API_BASE_URL", "SAHMK_REST_URL", "sahmk_rest_url"),
    )
    sahmk_data_mode: str = "delayed"
    sahmk_poll_seconds: float = Field(default=30, ge=5, le=600)
    sahmk_watchlist_poll_seconds: float = Field(default=20, ge=5, le=600)
    sahmk_market_scan_seconds: float = Field(default=90, ge=15, le=900)
    sahmk_batch_size: int = Field(default=4, ge=1, le=20)
    sahmk_request_gap_seconds: float = Field(default=0.4, ge=0.05, le=5)
    sahmk_cache_ttl_seconds: float = Field(default=180, ge=15, le=3600)
    sahmk_max_backoff_seconds: float = Field(default=120, ge=15, le=600)
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
    smtp_server: str = Field(
        default="smtp.gmail.com",
        validation_alias=AliasChoices("SMTP_SERVER", "smtp_server"),
    )
    smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("SMTP_PORT", "smtp_port"),
    )
    sender_email: str = Field(
        default="",
        validation_alias=AliasChoices("SENDER_EMAIL", "smtp_sender_email", "sender_email"),
    )
    sender_password: str = Field(
        default="",
        validation_alias=AliasChoices("SENDER_PASSWORD", "smtp_sender_password", "sender_password"),
    )
    alert_recipient_email: str = Field(
        default="alhwez@gmail.com",
        validation_alias=AliasChoices("ALERT_RECIPIENT_EMAIL", "alert_recipient_email"),
    )
    financial_sync_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("FINANCIAL_SYNC_ENABLED", "financial_sync_enabled"),
    )
    financial_sync_hour: int = Field(
        default=17,
        ge=0,
        le=23,
        validation_alias=AliasChoices("FINANCIAL_SYNC_HOUR", "financial_sync_hour"),
    )
    financial_sync_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias=AliasChoices("FINANCIAL_SYNC_MINUTE", "financial_sync_minute"),
    )
    financial_sync_run_on_startup: bool = Field(
        default=True,
        validation_alias=AliasChoices("FINANCIAL_SYNC_RUN_ON_STARTUP", "financial_sync_run_on_startup"),
    )
    tasi_scheduler_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("TASI_SCHEDULER_ENABLED", "tasi_scheduler_enabled"),
    )
    tasi_scan_interval_minutes: int = Field(
        default=2,
        ge=1,
        le=30,
        validation_alias=AliasChoices("TASI_SCAN_INTERVAL_MINUTES", "tasi_scan_interval_minutes"),
    )
    tasi_scan_limit: int = Field(
        default=12,
        ge=4,
        le=40,
        validation_alias=AliasChoices("TASI_SCAN_LIMIT", "tasi_scan_limit"),
    )
    tasi_open_hour: int = Field(default=9, ge=0, le=23)
    tasi_open_minute: int = Field(default=30, ge=0, le=59)
    tasi_close_hour: int = Field(default=15, ge=0, le=23)
    tasi_close_minute: int = Field(default=30, ge=0, le=59)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
