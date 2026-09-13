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
    source: str = "sahm"
    bars: int
    session: SessionFlow
    levels: MarketLevelsOut
    candles: list[CandleOut]


class RadarLiveResponse(BaseModel):
    symbol: str
    success: bool = True
    source: str = "Sahm API"
    analysis: dict[str, Any]


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
    source: str = "Sahm API"
    total_companies: int
    synced_at: str | None = None
    data: list[dict[str, Any]]


class SectorRotationResponse(BaseModel):
    success: bool = True
    source: str = "Sahm API"
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


class MarketRecommendationsResponse(BaseModel):
    success: bool = True
    count: int
    source: str = "Sahm API"
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
