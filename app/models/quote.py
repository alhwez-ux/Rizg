from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Quote(BaseModel):
    """Normalized top-of-book quote used across services and storage."""

    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str = Field(..., min_length=1, max_length=12)
    bid: float = Field(..., gt=0)
    ask: float = Field(..., gt=0)
    bid_size: float = Field(..., ge=0)
    ask_size: float = Field(..., ge=0)
    last_price: float | None = Field(default=None, gt=0)
    volume: float = Field(default=0, ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_spread(self) -> "Quote":
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        return self

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2
