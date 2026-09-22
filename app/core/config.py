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
    sahmk_board_cache_ttl_seconds: float = Field(
        default=900,
        ge=60,
        le=86_400,
        validation_alias=AliasChoices("SAHMK_BOARD_CACHE_TTL_SECONDS", "sahmk_board_cache_ttl_seconds"),
    )
    sahmk_daily_limit: int = Field(
        default=90,
        ge=10,
        le=10_000,
        validation_alias=AliasChoices("SAHMK_DAILY_LIMIT", "sahmk_daily_limit"),
    )
    sahmk_delayed_min_interval_seconds: float = Field(
        default=900,
        ge=60,
        le=86_400,
        validation_alias=AliasChoices("SAHMK_DELAYED_MIN_INTERVAL_SECONDS", "sahmk_delayed_min_interval_seconds"),
    )
    sahmk_max_backoff_seconds: float = Field(default=120, ge=15, le=600)
    sahmk_symbols: list[str] = Field(default_factory=lambda: ["4030"])
    screener_leader_limit: int = Field(default=10, ge=3, le=25)
    signal_net_flow_threshold: Decimal = Field(default=Decimal("3000"))
    signal_aggressive_ratio: Decimal = Field(default=Decimal("0.51"))
    signal_exit_net_ceiling: Decimal = Field(default=Decimal("0"))
    signal_atr_target_mult: Decimal = Field(default=Decimal("1.5"))
    signal_atr_stop_mult: Decimal = Field(default=Decimal("1.0"))
    signal_entry_share: float = Field(default=0.15, ge=0.05, le=0.5)
    signal_confirm_hits: int = Field(
        default=3,
        ge=1,
        le=8,
        validation_alias=AliasChoices("SIGNAL_CONFIRM_HITS", "signal_confirm_hits"),
    )
    signal_exit_confirm_hits: int = Field(
        default=3,
        ge=1,
        le=8,
        validation_alias=AliasChoices("SIGNAL_EXIT_CONFIRM_HITS", "signal_exit_confirm_hits"),
    )
    signal_sample_seconds: float = Field(
        default=45,
        ge=0,
        le=600,
        validation_alias=AliasChoices("SIGNAL_SAMPLE_SECONDS", "signal_sample_seconds"),
    )
    signal_entry_cooldown_seconds: float = Field(
        default=180,
        ge=0,
        le=3600,
        validation_alias=AliasChoices("SIGNAL_ENTRY_COOLDOWN_SECONDS", "signal_entry_cooldown_seconds"),
    )
    signal_exit_cooldown_seconds: float = Field(
        default=120,
        ge=0,
        le=3600,
        validation_alias=AliasChoices("SIGNAL_EXIT_COOLDOWN_SECONDS", "signal_exit_cooldown_seconds"),
    )
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
        default=False,
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
        default=False,
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
    tadawul_daily_sync_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("TADAWUL_DAILY_SYNC_ENABLED", "tadawul_daily_sync_enabled"),
    )
    tadawul_daily_sync_hour: int = Field(
        default=16,
        ge=0,
        le=23,
        validation_alias=AliasChoices("TADAWUL_DAILY_SYNC_HOUR", "tadawul_daily_sync_hour"),
    )
    tadawul_daily_sync_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias=AliasChoices("TADAWUL_DAILY_SYNC_MINUTE", "tadawul_daily_sync_minute"),
    )
    tadawul_daily_sync_on_startup: bool = Field(
        default=False,
        validation_alias=AliasChoices("TADAWUL_DAILY_SYNC_ON_STARTUP", "tadawul_daily_sync_on_startup"),
    )
    tadawul_daily_quote_limit: int = Field(
        default=250,
        ge=10,
        le=500,
        validation_alias=AliasChoices("TADAWUL_DAILY_QUOTE_LIMIT", "tadawul_daily_quote_limit"),
    )
    tickchart_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("TICKCHART_ENABLED", "tickchart_enabled"),
    )
    tickchart_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("TICKCHART_API_KEY", "tickchart_api_key"),
    )
    tickchart_rest_url: str = Field(
        default="",
        validation_alias=AliasChoices("TICKCHART_REST_URL", "tickchart_rest_url"),
    )
    tickchart_trades_ws: str = Field(
        default="wss://api.sahmk.sa/ws/v1/market/trades/",
        validation_alias=AliasChoices("TICKCHART_TRADES_WS", "tickchart_trades_ws"),
    )
    tickchart_depth_ws: str = Field(
        default="wss://api.sahmk.sa/ws/v1/market/depth/",
        validation_alias=AliasChoices("TICKCHART_DEPTH_WS", "tickchart_depth_ws"),
    )
    tickchart_symbols: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("TICKCHART_SYMBOLS", "tickchart_symbols"),
    )
    tickchart_ping_seconds: float = Field(
        default=30,
        ge=5,
        le=120,
        validation_alias=AliasChoices("TICKCHART_PING_SECONDS", "tickchart_ping_seconds"),
    )
    tickchart_depth_levels: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices("TICKCHART_DEPTH_LEVELS", "tickchart_depth_levels"),
    )
    tickchart_poll_seconds: float = Field(
        default=3,
        ge=1,
        le=60,
        validation_alias=AliasChoices("TICKCHART_POLL_SECONDS", "tickchart_poll_seconds"),
    )
    tickchart_ingest_token: str = Field(
        default="",
        validation_alias=AliasChoices("TICKCHART_INGEST_TOKEN", "tickchart_ingest_token"),
    )
    tickchart_block_value: float = Field(
        default=500000,
        ge=10000,
        le=50_000_000,
        validation_alias=AliasChoices("TICKCHART_BLOCK_VALUE", "tickchart_block_value"),
    )
    tickchart_autosync_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("TICKCHART_AUTOSYNC_ENABLED", "tickchart_autosync_enabled"),
    )
    tickchart_export_dir: str = Field(
        default="",
        validation_alias=AliasChoices("TICKCHART_EXPORT_DIR", "tickchart_export_dir"),
    )
    tickchart_export_poll_seconds: float = Field(
        default=0.5,
        ge=0.2,
        le=10,
        validation_alias=AliasChoices("TICKCHART_EXPORT_POLL_SECONDS", "tickchart_export_poll_seconds"),
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
