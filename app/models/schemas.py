from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.quote import Quote
from app.models.trade import SessionFlow


class QuoteIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    symbol: str = Field(..., min_length=1, max_length=12, examples=["AAPL"])
    bid: float = Field(..., gt=0, examples=[189.12])
    ask: float = Field(..., gt=0, examples=[189.18])
    bid_size: float = Field(..., ge=0, examples=[1200])
    ask_size: float = Field(..., ge=0, examples=[800])
    last_price: float | None = Field(default=None, gt=0, examples=[189.15])
    volume: float = Field(default=0, ge=0, examples=[1_250_000])
    timestamp: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_spread(self) -> "QuoteIn":
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        return self

    def to_quote(self) -> Quote:
        payload = self.model_dump(exclude_none=True)
        return Quote.model_validate(payload)


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    last_price: float | None
    volume: float
    timestamp: datetime
    mid_price: float


class LiquiditySnapshot(BaseModel):
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    last_price: float | None
    volume: float
    mid_price: float
    spread: float
    spread_bps: float
    relative_spread: float
    quoted_depth: float
    effective_spread: float | None
    timestamp: datetime


class LiquidityStats(BaseModel):
    symbol: str
    observations: int
    avg_spread: float
    avg_spread_bps: float
    min_spread: float
    max_spread: float
    avg_quoted_depth: float
    avg_volume: float
    vwap: float | None = None
    window_start: datetime
    window_end: datetime


class QuoteHistoryResponse(BaseModel):
    symbol: str
    count: int
    quotes: list[QuoteOut]


class SymbolListResponse(BaseModel):
    symbols: list[str]
    count: int


class CandleOut(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketLevelsOut(BaseModel):
    symbol: str
    vwap: float | None = None
    atr: float | None = None
    last_price: float | None = None
    session_high: float | None = None
    session_low: float | None = None
    book_pressure: float | None = None


class AnalyzeResponse(BaseModel):
    symbol: str
    interval: str
    source: str = "TickChart"
    bars: int
    session: SessionFlow
    levels: MarketLevelsOut
    candles: list[CandleOut]


class RadarLiveResponse(BaseModel):
    symbol: str
    success: bool = True
    source: str = "TickChart"
    analysis: dict[str, Any]


class TickChartIngestResponse(BaseModel):
    success: bool = True
    ingested: int = 0
    source: str = "TickChart"


class TickChartStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    trades_live: bool = False
    depth_live: bool = False
    symbols: list[str] = Field(default_factory=list)
    source: str = "TickChart"
    mode: str = "cloud"
    autosync_enabled: bool = False
    autosync_watching: bool = False
    autosync_dirs: list[str] = Field(default_factory=list)
    autosync_files: int = 0
    last_file: str | None = None
    last_ingested: int = 0
    last_sync_at: str | None = None
    quote_mode: str = "waiting"
    last_quotes: int = 0
    price_source: str = "TickChart"
    sahm_quota: dict[str, Any] | None = None


class TickChartFollowBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=80)


class TickChartUploadText(BaseModel):
    filename: str = "upload.csv"
    content: str
    symbol: str | None = None


class ComplianceSyncItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    symbol: str = Field(..., min_length=1, max_length=12)
    name: str | None = None
    companyNameAr: str | None = None
    currentStatus: str | None = None
    status: str | None = None
    category: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()


class ComplianceChangeOut(BaseModel):
    symbol: str
    name: str
    old_category: str
    new_category: str


class ComplianceSyncRequest(BaseModel):
    items: list[ComplianceSyncItem] = Field(default_factory=list)


class ComplianceSyncResponse(BaseModel):
    updated: int
    changes: list[ComplianceChangeOut]


class RankingMatrixResponse(BaseModel):
    success: bool = True
    message: str | None = None
    source: str = "TickChart"
    total_companies: int
    synced_at: str | None = None
    data: list[dict[str, Any]]


class SectorRotationResponse(BaseModel):
    success: bool = True
    source: str = "TickChart"
    quote_mode: str = "waiting"
    total_sectors: int
    leaders: list[dict[str, Any]]
    laggards: list[dict[str, Any]]
    data: list[dict[str, Any]]
    sectors: list[dict[str, Any]]


class SectorCompaniesResponse(BaseModel):
    success: bool = True
    sector: str
    total_companies: int
    companies: list[dict[str, Any]]


class MarketRecommendation(BaseModel):
    symbol: str
    name: str
    close_price: float
    signal_type: str
    signal_kind: str = "momentum"
    confidence: str
    confidence_score: int = 0
    entry_price: str
    target_price: str
    stop_loss: str
    reason: str
    volume_ratio: float | None = None
    mfi: float | None = None
    scan_mode: str | None = None
    horizon: str | None = None
    entry: bool = False
    entry_rule: str | None = None
    last_price: float | None = None
    entry_locked_at: str | None = None
    target_hit: bool = False
    stop_hit: bool = False


class MarketRecommendationsResponse(BaseModel):
    success: bool = True
    count: int
    source: str = "TickChart"
    scan_mode: str = "end_of_day"
    session_phase: str | None = None
    session_label: str | None = None
    scan_build: str = "smc-long-1"
    total: int = 0
    data: list[MarketRecommendation]


class TriggerTestAlertResponse(BaseModel):
    success: bool = True
    message: str


class SchedulerJobStatus(BaseModel):
    id: str
    next_run_at: str | None = None


class SchedulerStatusResponse(BaseModel):
    success: bool = True
    enabled: bool
    running: bool
    timezone: str
    clock: str
    phase: str
    phase_label: str
    intraday: bool
    jobs: list[SchedulerJobStatus] = Field(default_factory=list)
    last: dict[str, Any] = Field(default_factory=dict)


class SchedulerRunResponse(BaseModel):
    success: bool = True
    job: str
    result: dict[str, Any]


class DailySyncStatusResponse(BaseModel):
    success: bool = True
    enabled: bool
    running: bool
    timezone: str
    clock: str
    hour: int
    minute: int
    phase: str
    phase_label: str
    as_of: str | None = None
    symbols: int = 0
    jobs: list[SchedulerJobStatus] = Field(default_factory=list)
    last: dict[str, Any] = Field(default_factory=dict)


class DividendRow(BaseModel):
    symbol: str
    name: str
    sector: str = ""
    cash_dividend: float
    eligibility_date: str
    payment_date: str
    shariah_status: str | None = None
    shariah_label: str = ""
    days_to_eligibility: int = 0


class DividendsResponse(BaseModel):
    success: bool = True
    count: int = 0
    as_of: str
    timezone: str = "Asia/Riyadh"
    hint: str = "تُحذف الشركة تلقائياً بعد مرور تاريخ الأحقية"
    data: list[DividendRow] = Field(default_factory=list)


class PreOpenRow(BaseModel):
    symbol: str
    name: str
    sector: str = ""
    expected_open: float | None = None
    prev_close: float | None = None
    open_variation_pct: float | None = None
    buy_volume: float = 0
    sell_volume: float = 0
    book_imbalance: float | None = None
    buy_share: float | None = None
    block_trades: int = 0
    last_block_value: float | None = None
    large_block_side: str | None = None
    signal: str
    signal_kind: str
    liquidity_state: str
    score: float = 0


class PreOpenScanResponse(BaseModel):
    success: bool = True
    session_phase: str
    session_label: str
    in_window: bool
    window_start: str = "09:30"
    window_end: str = "10:00"
    timezone: str = "Asia/Riyadh"
    source: str = "TickChart"
    count: int = 0
    accumulation_count: int = 0
    distribution_count: int = 0
    hint: str = ""
    scanned_at: str
    data: list[PreOpenRow] = Field(default_factory=list)


class SmartMoneyRow(BaseModel):
    symbol: str
    name: str
    sector: str = ""
    last_price: float | None = None
    institutional_flow_score: float = 0
    inst_share_pct: float = 0
    retail_share_pct: float = 0
    institutional_mfi: float | None = None
    retail_mfi: float | None = None
    block_trades: int = 0
    last_block_value: float | None = None
    clustered: int = 0
    clustered_buys: int = 0
    cluster_run: int = 0
    near_bid_wall: bool = False
    bid_wall: dict[str, float] | None = None
    ask_wall: dict[str, float] | None = None
    signal: str
    signal_kind: str
    badge: str
    reason: str = ""
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    plan_ok: bool = False
    score: float = 0


class SmartMoneyScanResponse(BaseModel):
    success: bool = True
    session_phase: str
    session_label: str
    source: str = "TickChart"
    count: int = 0
    accumulation_count: int = 0
    distribution_count: int = 0
    watch_count: int = 0
    hint: str = ""
    scanned_at: str
    data: list[SmartMoneyRow] = Field(default_factory=list)


class RecoveryPlanRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str = Field(..., min_length=1, max_length=12, examples=["1120"])
    quantity: float = Field(..., gt=0, examples=[500])
    avg_price: float = Field(..., gt=0, examples=[95.4])

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class RecoveryPosition(BaseModel):
    symbol: str
    name: str
    sector: str = ""
    quantity: float
    avg_price: float
    last_price: float
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    loss_amount: float
    pnl_pct: float
    in_loss: bool


class RecoveryAverage(BaseModel):
    recommended: bool = True
    extra_quantity: int
    extra_cost: float
    new_quantity: float
    new_avg_price: float
    entry: float
    target: float
    stop: float
    reason: str = ""


class RecoveryAllocation(BaseModel):
    symbol: str
    name: str
    sector: str = ""
    score: float = 0
    tags: list[str] = Field(default_factory=list)
    weight_pct: float = 0
    allocation: float
    shares: int
    entry: float
    target: float
    stop: float
    expected_gain: float = 0
    reason: str = ""


class RecoveryPlanResponse(BaseModel):
    success: bool = True
    session_phase: str
    session_label: str
    source: str = "TickChart"
    stance: str
    stance_label: str
    hint: str = ""
    scanned_at: str
    position: RecoveryPosition
    averaging: RecoveryAverage | None = None
    rotation_budget: float = 0
    expected_recovery: float = 0
    cover_pct: float = 0
    count: int = 0
    data: list[RecoveryAllocation] = Field(default_factory=list)


class ShariahScreenRow(BaseModel):
    symbol: str
    name: str
    sector: str = ""
    status: str
    status_ar: str = ""
    debt_ratio: float | None = None
    impure_income_ratio: float | None = None
    purification_rate: float | None = None


class ShariahScreenResponse(BaseModel):
    success: bool = True
    filter: str = "all"
    count: int = 0
    data: list[ShariahScreenRow] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class WsSubscribeMessage(BaseModel):
    action: str = Field(..., examples=["subscribe"])
    symbols: list[str] = Field(default_factory=list)

    @field_validator("action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        return value.lower().strip()

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        return [symbol.upper().strip() for symbol in values if symbol.strip()]
