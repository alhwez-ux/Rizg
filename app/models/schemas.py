from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.quote import Quote


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
