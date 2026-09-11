from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TickType(str, Enum):
    UPTICK = "uptick"
    DOWNTICK = "downtick"
    ZERO_TICK = "zero_tick"
    UNCLASSIFIED = "unclassified"


class SessionFlow(BaseModel):
    """Accumulated tick-rule money flow for one ticker in the current session."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    inflow: Decimal
    outflow: Decimal
    net_flow: Decimal
    last_price: Decimal | None
    last_different_price: Decimal | None
    last_side: TradeSide | None
    trade_count: int
    classified_count: int
    buy_volume: Decimal = Decimal("0")
    sell_volume: Decimal = Decimal("0")


class TradeResult(BaseModel):
    """Classification and session totals produced by a single processed trade."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: TradeSide | None
    tick: TickType
    price: Decimal
    volume: Decimal
    money_flow: Decimal = Field(
        description="Signed contribution: +price*volume for BUY, -price*volume for SELL."
    )
    timestamp: datetime | None = None
    session: SessionFlow


class LiquidityStreamMessage(BaseModel):
    """WebSocket payload for live net-flow and buy/sell volume."""

    model_config = ConfigDict(frozen=True)

    type: Literal["liquidity", "snapshot"] = "liquidity"
    symbol: str
    net_flow: Decimal
    inflow: Decimal
    outflow: Decimal
    buy_volume: Decimal
    sell_volume: Decimal
    last_price: Decimal | None = None
    last_side: TradeSide | None = None
    tick: TickType | None = None
    side: TradeSide | None = None
    price: Decimal | None = None
    volume: Decimal | None = None
    money_flow: Decimal | None = None
    trade_count: int = 0
    timestamp: datetime | None = None

    def as_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_trade(cls, result: TradeResult) -> "LiquidityStreamMessage":
        session = result.session
        return cls(
            type="liquidity",
            symbol=result.symbol,
            net_flow=session.net_flow,
            inflow=session.inflow,
            outflow=session.outflow,
            buy_volume=session.buy_volume,
            sell_volume=session.sell_volume,
            last_price=session.last_price,
            last_side=session.last_side,
            tick=result.tick,
            side=result.side,
            price=result.price,
            volume=result.volume,
            money_flow=result.money_flow,
            trade_count=session.trade_count,
            timestamp=result.timestamp,
        )

    @classmethod
    def from_session(
        cls,
        session: SessionFlow,
        *,
        timestamp: datetime | None = None,
    ) -> "LiquidityStreamMessage":
        return cls(
            type="snapshot",
            symbol=session.symbol,
            net_flow=session.net_flow,
            inflow=session.inflow,
            outflow=session.outflow,
            buy_volume=session.buy_volume,
            sell_volume=session.sell_volume,
            last_price=session.last_price,
            last_side=session.last_side,
            trade_count=session.trade_count,
            timestamp=timestamp,
        )
