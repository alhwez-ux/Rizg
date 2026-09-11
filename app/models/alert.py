from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertKind(str, Enum):
    INFLOW_SURGE = "inflow_surge"
    VOLUME_SURGE = "volume_surge"
    NET_FLOW_SPIKE = "net_flow_spike"
    OUTFLOW_SURGE = "outflow_surge"


class LiquidityAlert(BaseModel):
    """A 1-minute liquidity surge detected for a tracked symbol."""

    model_config = ConfigDict(frozen=True)

    type: Literal["alert"] = "alert"
    id: str
    symbol: str
    kind: AlertKind
    title: str
    message: str
    window_seconds: int
    window_inflow: Decimal
    window_outflow: Decimal = Decimal("0")
    window_volume: Decimal
    window_net_flow: Decimal
    session_inflow: Decimal = Decimal("0")
    session_outflow: Decimal = Decimal("0")
    last_price: Decimal | None = None
    timestamp: datetime
    cooldown_seconds: int = Field(default=0, ge=0)

    def as_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AlertListResponse(BaseModel):
    count: int
    alerts: list[LiquidityAlert]
