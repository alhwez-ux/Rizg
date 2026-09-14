from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_SYMBOL_RE = re.compile(r"^\d{4}$")
_MAIN_MARKET_RE = re.compile(r"^[1-8]\d{3}$")


def normalize_tasi_symbol(value: str) -> str:
    symbol = value.strip().translate(_ARABIC_DIGITS).upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError(symbol)
    return symbol


def is_tasi_main_symbol(value: str) -> bool:
    """True for Tadawul main-market equities (1xxx–8xxx), not Nomu/ETF 9xxx."""

    ticker = str(value or "").strip().translate(_ARABIC_DIGITS).upper()
    return bool(_MAIN_MARKET_RE.fullmatch(ticker))


class WatchlistItemIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str = Field(..., min_length=1, max_length=8)

    @field_validator("symbol")
    @classmethod
    def normalize(cls, value: str) -> str:
        try:
            return normalize_tasi_symbol(value)
        except ValueError as exc:
            raise ValueError("استخدم رمز تداول من 4 أرقام مثل 4030") from exc


class WatchlistResponse(BaseModel):
    symbols: list[str]
    count: int


class ScreenerRow(BaseModel):
    symbol: str
    name: str = ""
    price: Decimal = Decimal("0")
    change_percent: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    value: Decimal = Decimal("0")
    inflow: Decimal = Decimal("0")
    outflow: Decimal = Decimal("0")
    net_flow: Decimal = Decimal("0")
    buy_volume: Decimal = Decimal("0")
    sell_volume: Decimal = Decimal("0")
    buy_ratio: Decimal | None = None
    sell_ratio: Decimal | None = None
    volume_surge: Decimal | None = None
    score: Decimal = Decimal("0")
    entry_signal: bool = False
    exit_signal: bool = False
    unexpected: bool = False
    flow_verified: bool = False
    tracked: bool = False
    vwap: Decimal | None = None
    atr: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    book_pressure: Decimal | None = None
    suggested_entry: Decimal | None = None
    suggested_exit: Decimal | None = None
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None
    reasons: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class MarketPulse(BaseModel):
    index: str = "TASI"
    index_value: Decimal | None = None
    index_change_percent: Decimal | None = None
    advancing: int | None = None
    declining: int | None = None
    delayed: bool = True


class ScreenerSnapshot(BaseModel):
    watchlist: list[ScreenerRow]
    radar: list[ScreenerRow]
    pulse: MarketPulse
    scanned: int
    delayed: bool = True
    updated_at: datetime | None = None
