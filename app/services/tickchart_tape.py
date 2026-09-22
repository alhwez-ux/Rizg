"""Live TickChart tape: Level-2 book, block prints, institutional MFI, traps."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from app.models.trade import TradeSide

ZERO = Decimal("0")
_PRINT_WINDOW = 40
_BLOCK_MULT = Decimal("4")
_VOLUME_SPIKE = Decimal("2")
_SILENT_RATIO = Decimal("0.6")
_WALL_MULT = Decimal("3")


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _json(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


@dataclass
class BookLevel:
    price: Decimal
    quantity: Decimal


@dataclass
class SymbolTape:
    symbol: str
    prices: deque[Decimal] = field(default_factory=lambda: deque(maxlen=_PRINT_WINDOW))
    quantities: deque[Decimal] = field(default_factory=lambda: deque(maxlen=_PRINT_WINDOW))
    values: deque[Decimal] = field(default_factory=lambda: deque(maxlen=_PRINT_WINDOW))
    sides: deque[TradeSide | None] = field(default_factory=lambda: deque(maxlen=_PRINT_WINDOW))
    bids: list[BookLevel] = field(default_factory=list)
    asks: list[BookLevel] = field(default_factory=list)
    inst_inflow: Decimal = ZERO
    inst_outflow: Decimal = ZERO
    retail_inflow: Decimal = ZERO
    retail_outflow: Decimal = ZERO
    session_quantity: Decimal = ZERO
    session_value: Decimal = ZERO
    block_trades: int = 0
    last_block_value: Decimal | None = None
    prev_close: Decimal | None = None

    def observe_print(
        self,
        price: Decimal,
        quantity: Decimal,
        *,
        side: TradeSide | None,
        block_floor: Decimal,
    ) -> dict[str, Any]:
        value = price * quantity
        self.prices.append(price)
        self.quantities.append(quantity)
        self.values.append(value)
        self.sides.append(side)
        self.session_quantity += quantity
        self.session_value += value
        institutional = _is_block(value, quantity, self.values, self.quantities, block_floor)
        if institutional:
            self.block_trades += 1
            self.last_block_value = value
            if side == TradeSide.BUY:
                self.inst_inflow += value
            elif side == TradeSide.SELL:
                self.inst_outflow += value
        else:
            if side == TradeSide.BUY:
                self.retail_inflow += value
            elif side == TradeSide.SELL:
                self.retail_outflow += value
        return {
            "block": institutional,
            "value": value,
            "volume_ratio": self.volume_ratio(),
        }

    def observe_book(self, bids: list[BookLevel], asks: list[BookLevel]) -> None:
        self.bids = bids[:20]
        self.asks = asks[:20]

    def volume_ratio(self) -> Decimal | None:
        if len(self.quantities) < 8:
            return None
        recent = list(self.quantities)[-5:]
        baseline = list(self.quantities)[:-5]
        if not baseline:
            return None
        avg = sum(baseline, ZERO) / Decimal(len(baseline))
        if avg <= ZERO:
            return None
        return (sum(recent, ZERO) / Decimal(len(recent))) / avg

    def mfi(self, inflow: Decimal, outflow: Decimal) -> Decimal | None:
        total = inflow + outflow
        if total <= ZERO:
            return None
        return (inflow / total) * Decimal("100")

    def institutional_mfi(self) -> Decimal | None:
        return self.mfi(self.inst_inflow, self.inst_outflow)

    def retail_mfi(self) -> Decimal | None:
        return self.mfi(self.retail_inflow, self.retail_outflow)

    def blended_mfi(self) -> Decimal | None:
        inst = self.institutional_mfi()
        retail = self.retail_mfi()
        if inst is None and retail is None:
            return None
        if inst is None:
            return retail
        if retail is None:
            return inst
        return inst * Decimal("0.7") + retail * Decimal("0.3")

    def bid_wall(self) -> BookLevel | None:
        return _wall(self.bids)

    def ask_wall(self) -> BookLevel | None:
        return _wall(self.asks)

    def bid_size(self) -> Decimal:
        return sum((level.quantity for level in self.bids[:5]), ZERO)

    def ask_size(self) -> Decimal:
        return sum((level.quantity for level in self.asks[:5]), ZERO)

    def detect_trap(self) -> dict[str, str] | None:
        ratio = self.volume_ratio()
        bid_wall = self.bid_wall()
        ask_wall = self.ask_wall()
        last_side = self.sides[-1] if self.sides else None
        spike = ratio is not None and ratio >= _VOLUME_SPIKE
        silent = _is_silent(self.quantities)
        rising = _is_rising(self.prices)
        inst = self.institutional_mfi() or Decimal("50")

        if spike and ask_wall is not None and last_side == TradeSide.BUY:
            return {
                "kind": "bull_trap",
                "label": "فخ صعود: تضاعف الحجم اللحظي مقابل جدار عرض (Level 2)",
            }
        if spike and bid_wall is not None and last_side == TradeSide.SELL:
            return {
                "kind": "bear_trap",
                "label": "فخ هبوط: تضاعف الحجم اللحظي مقابل جدار طلب (Level 2)",
            }
        hidden = self.detect_iceberg() or self.detect_hidden_accumulation()
        if hidden is not None:
            return hidden
        if silent and bid_wall is not None and rising and inst >= Decimal("55"):
            return {
                "kind": "silent_accumulation",
                "label": "تجميع صامت: سيولة مؤسسية خلف جدار الطلب مع هدوء في التكات",
            }
        if silent and ask_wall is not None and not rising and inst <= Decimal("45"):
            return {
                "kind": "silent_distribution",
                "label": "تصريف صامت: جدار عرض مع سيولة مؤسسية خارجة",
            }
        return None

    def cluster_stats(self) -> dict[str, Any]:
        """Count institutional-size prints parked near support or the bid wall."""

        empty = {
            "clustered": 0,
            "clustered_buys": 0,
            "clustered_sells": 0,
            "cluster_run": 0,
            "support": None,
            "near_bid_wall": False,
        }
        if len(self.prices) < 8 or len(self.quantities) < 8:
            return empty
        bid_wall = self.bid_wall()
        support = bid_wall.price if bid_wall is not None else min(self.prices)
        if support <= ZERO:
            return empty
        typical = median(self.quantities)
        if typical <= ZERO:
            return empty
        band = support * Decimal("0.008")
        clustered = 0
        clustered_buy = 0
        clustered_sell = 0
        run = 0
        max_run = 0
        near_bid_wall = False
        for price, qty, side in zip(self.prices, self.quantities, self.sides):
            large = qty >= typical * Decimal("2")
            near_support = abs(price - support) <= band
            near_bid = bid_wall is not None and abs(price - bid_wall.price) <= band
            if not (large and (near_support or near_bid)):
                run = 0
                continue
            clustered += 1
            run += 1
            if run > max_run:
                max_run = run
            if side == TradeSide.BUY:
                clustered_buy += 1
            elif side == TradeSide.SELL:
                clustered_sell += 1
            if near_bid:
                near_bid_wall = True
        return {
            "clustered": clustered,
            "clustered_buys": clustered_buy,
            "clustered_sells": clustered_sell,
            "cluster_run": max_run,
            "support": float(support),
            "near_bid_wall": near_bid_wall,
        }

    def detect_hidden_accumulation(self) -> dict[str, str] | None:
        """Clustered block prints parked on the bid / swing low before a break."""

        if len(self.prices) < 12 or len(self.quantities) < 12:
            return None
        stats = self.cluster_stats()
        if stats["clustered"] < 3 or stats["clustered_buys"] < 2:
            return None
        support = _dec(stats.get("support"))
        if support is None or support <= ZERO:
            return None
        last = self.prices[-1]
        if last > support * Decimal("1.025"):
            return None
        inst = self.institutional_mfi() or Decimal("50")
        if inst < Decimal("52"):
            return None
        return {
            "kind": "hidden_accumulation",
            "label": "تجميع مؤسسي خفي: صفقات كبيرة متجمعة قرب الدعم وجدار الطلب قبل الاختراق",
        }

    def detect_iceberg(self) -> dict[str, str] | None:
        """Volume surge absorbed in a tight range — iceberg / hidden institutional buying."""

        ratio = self.volume_ratio()
        if ratio is None or ratio < Decimal("1.5"):
            return None
        if len(self.prices) < 8:
            return None
        last = self.prices[-1]
        if last <= ZERO:
            return None
        low = min(self.prices)
        high = max(self.prices)
        compressed = (high - low) / last <= Decimal("0.018")
        supported = abs(last - low) <= last * Decimal("0.008")
        if not (compressed or supported):
            return None
        inst = self.institutional_mfi()
        if inst is not None and inst < Decimal("48"):
            return None
        return {
            "kind": "hidden_accumulation",
            "label": "تجميع مؤسسي خفي: حجم يتجاوز 150% من المتوسط مع ضغط سعري عند الدعم (أوامر جبل الجليد)",
        }

    def snapshot(self) -> dict[str, Any]:
        trap = self.detect_trap()
        clusters = self.cluster_stats()
        bid = self.bids[0].price if self.bids else None
        ask = self.asks[0].price if self.asks else None
        last = self.prices[-1] if self.prices else None
        change = None
        if last is not None and self.prev_close and self.prev_close > ZERO:
            change = ((last - self.prev_close) / self.prev_close) * Decimal("100")
        return {
            "mfi": _json(self.blended_mfi()),
            "institutional_mfi": _json(self.institutional_mfi()),
            "retail_mfi": _json(self.retail_mfi()),
            "institutional_inflow": _json(self.inst_inflow),
            "institutional_outflow": _json(self.inst_outflow),
            "retail_inflow": _json(self.retail_inflow),
            "retail_outflow": _json(self.retail_outflow),
            "volume_ratio": _json(self.volume_ratio()),
            "block_trades": self.block_trades,
            "last_block_value": _json(self.last_block_value),
            "clustered": clusters["clustered"],
            "clustered_buys": clusters["clustered_buys"],
            "clustered_sells": clusters["clustered_sells"],
            "cluster_run": clusters["cluster_run"],
            "support": clusters["support"],
            "near_bid_wall": clusters["near_bid_wall"],
            "session_volume": _json(self.session_quantity),
            "session_value": _json(self.session_value),
            "bid_wall": _level_json(self.bid_wall()),
            "ask_wall": _level_json(self.ask_wall()),
            "levels": {
                "bids": [_level_json(level) for level in self.bids[:10]],
                "asks": [_level_json(level) for level in self.asks[:10]],
            },
            "trap": trap,
            "last_price": _json(last),
            "change_percent": _json(change),
            "bid": _json(bid),
            "ask": _json(ask),
        }


def parse_book_levels(raw: Any) -> list[BookLevel]:
    levels: list[BookLevel] = []
    if not isinstance(raw, list):
        return levels
    for item in raw:
        price = None
        qty = None
        if isinstance(item, dict):
            price = _dec(item.get("price") or item.get("p") or item.get("bid") or item.get("ask"))
            qty = _dec(item.get("quantity") or item.get("size") or item.get("q") or item.get("volume"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            price = _dec(item[0])
            qty = _dec(item[1])
        if price is None or qty is None or price <= ZERO or qty < ZERO:
            continue
        levels.append(BookLevel(price=price, quantity=qty))
    return levels


def _is_block(
    value: Decimal,
    quantity: Decimal,
    values: deque[Decimal],
    quantities: deque[Decimal],
    block_floor: Decimal,
) -> bool:
    sample_values = list(values)[:-1]
    sample_qty = list(quantities)[:-1]
    median_value = median(sample_values) if len(sample_values) >= 5 else ZERO
    median_qty = median(sample_qty) if len(sample_qty) >= 5 else ZERO
    if value >= block_floor:
        return True
    if median_value > ZERO and value >= median_value * _BLOCK_MULT:
        return True
    if median_qty > ZERO and quantity >= median_qty * _BLOCK_MULT:
        return True
    return False


def _wall(levels: list[BookLevel]) -> BookLevel | None:
    if len(levels) < 3:
        return None
    sizes = [level.quantity for level in levels[:10]]
    typical = median(sizes) if sizes else ZERO
    if typical <= ZERO:
        return None
    for level in levels[:10]:
        if level.quantity >= typical * _WALL_MULT:
            return level
    return None


def _is_silent(quantities: deque[Decimal]) -> bool:
    if len(quantities) < 12:
        return False
    recent = list(quantities)[-8:]
    baseline = list(quantities)[:-8]
    avg = sum(baseline, ZERO) / Decimal(len(baseline))
    if avg <= ZERO:
        return False
    recent_avg = sum(recent, ZERO) / Decimal(len(recent))
    return recent_avg <= avg * _SILENT_RATIO


def _is_rising(prices: deque[Decimal]) -> bool:
    if len(prices) < 4:
        return False
    return prices[-1] >= prices[0]


def _level_json(level: BookLevel | None) -> dict[str, float] | None:
    if level is None:
        return None
    return {"price": float(level.price), "quantity": float(level.quantity)}
