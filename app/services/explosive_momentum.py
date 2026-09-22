"""Explosive momentum and accumulation: volume spikes, aggressive ask flow, breakouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from app.models.trade import TradeSide
from app.services.institutional_strategy import (
    SUPPORT_BAND,
    VOLUME_WINDOW,
    aggressive_buy_confirmed,
    volume_profile_average,
)

WATCH_FLAG = "تحت المراقبة"
EXPLOSIVE_FLAG = "تحت المراقبة - انفجار محتمل"
HIDDEN_ACCUM_FLAG = "تجميع مؤسسي خفي"
HIDDEN_TRAP_KINDS = frozenset({"hidden_accumulation", "silent_accumulation"})
VOLUME_SURGE_RATIO = Decimal("1.5")  # current >= 150% of 10-session / minute baseline
COMPRESSED_RANGE_PCT = Decimal("0.018")
COMPRESSED_CHANGE_PCT = Decimal("1.8")
DUMP_CHANGE_PCT = Decimal("-1.2")
MIN_AGGRESSIVE_BUY = Decimal("0.55")
BREAKOUT_MARGIN = Decimal("1.001")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class ExplosiveInputs:
    symbol: str
    name: str = ""
    price: Decimal | None = None
    volume: Decimal | None = None
    window_volumes: tuple[Any, ...] = ()
    minute_volume_ratio: Decimal | None = None
    session_high: Decimal | None = None
    session_low: Decimal | None = None
    prev_close: Decimal | None = None
    session_open: Decimal | None = None
    change_percent: Decimal | None = None
    net_flow: Decimal | None = None
    inflow: Decimal | None = None
    outflow: Decimal | None = None
    buy_volume: Decimal | None = None
    sell_volume: Decimal | None = None
    last_side: str | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    prior_closes: tuple[Any, ...] = ()
    support: Decimal | None = None
    bid_wall_price: Decimal | None = None
    near_bid_wall: bool = False
    clustered_buys: int = 0
    institutional_mfi: Decimal | None = None
    trap_kind: str | None = None


@dataclass(frozen=True)
class ExplosiveDecision:
    watch: bool
    explosive: bool
    flag: str | None
    volume_ratio: Decimal | None
    compressed: bool
    upward: bool
    aggressive_buy: bool
    flow_spike: bool
    resistance_break: bool
    hidden_accumulation: bool = False
    supported: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)
    score: Decimal = _ZERO


def evaluate_explosive(inputs: ExplosiveInputs) -> ExplosiveDecision:
    """Flag iceberg hidden accumulation, volume+tight tape, or an explosive ask-side breakout."""

    reasons: list[str] = []
    ratio = _volume_ratio(inputs)
    compressed = _range_compressed(inputs)
    supported = _held_at_support(inputs)
    upward = _upward_tape(inputs)
    dumping = _dumping(inputs)
    aggressive = _aggressive_ask_flow(inputs)
    flow_spike = _net_flow_spike(inputs)
    resistance = _local_resistance(inputs.prior_closes)
    breakout = _breaks_resistance(inputs.price, resistance)
    volume_ok = ratio is not None and ratio >= VOLUME_SURGE_RATIO
    iceberg = bool(volume_ok and not dumping and (compressed or supported))

    if dumping:
        reasons.append("تدفق هابط مع مدى سعري واسع — ليس تجميعاً")
        return ExplosiveDecision(
            watch=False,
            explosive=False,
            flag=None,
            volume_ratio=ratio,
            compressed=compressed,
            upward=upward,
            aggressive_buy=aggressive,
            flow_spike=flow_spike,
            resistance_break=breakout,
            hidden_accumulation=False,
            supported=supported,
            reasons=tuple(reasons),
        )

    if volume_ok:
        pct = int((ratio or _ZERO) * _HUNDRED)
        reasons.append(f"ارتفاع الحجم إلى {pct}% من متوسط 10 جلسات / الدقيقة")
    if compressed:
        reasons.append("المدى السعري مضغوط أثناء تدفق الكمية — امتصاص أوامر مخفية")
    if supported:
        reasons.append("السعر ممسوك عند الدعم / جدار الطلب رغم تدفق الكمية")
    if upward:
        reasons.append("الحركة السعرية صاعدة أو مستقرة")
    if aggressive:
        reasons.append("شراء عدواني عند سعر العرض (Ask)")
    if flow_spike:
        reasons.append("صافي تدفق الأموال موجب بقوة")
    if breakout and resistance is not None:
        reasons.append(f"كسر مقاومة محلية عند {resistance}")
    if inputs.clustered_buys >= 3 or inputs.near_bid_wall:
        reasons.append("كتل شرائية متجمعة قرب جدار الطلب")
    trap_kind = str(inputs.trap_kind or "").strip()
    if trap_kind in HIDDEN_TRAP_KINDS:
        reasons.append("أثر تجميع خفي على شريط التداول")

    watch = bool(volume_ok and (compressed or upward or supported))
    explosive = bool(watch and aggressive and flow_spike and breakout)
    if explosive:
        reasons.insert(0, EXPLOSIVE_FLAG)
        score = Decimal("8.5") + min((ratio or _ONE) - VOLUME_SURGE_RATIO, Decimal("3"))
        return ExplosiveDecision(
            watch=True,
            explosive=True,
            flag=EXPLOSIVE_FLAG,
            volume_ratio=ratio,
            compressed=compressed,
            upward=upward,
            aggressive_buy=aggressive,
            flow_spike=flow_spike,
            resistance_break=True,
            hidden_accumulation=iceberg,
            supported=supported,
            reasons=tuple(reasons),
            score=score,
        )
    if iceberg:
        reasons.insert(0, HIDDEN_ACCUM_FLAG)
        score = Decimal("6.5") + min((ratio or _ONE) - VOLUME_SURGE_RATIO, Decimal("2"))
        if inputs.near_bid_wall or inputs.clustered_buys >= 3:
            score += Decimal("0.8")
        if (inputs.institutional_mfi or Decimal("50")) >= Decimal("55"):
            score += Decimal("0.6")
        return ExplosiveDecision(
            watch=True,
            explosive=False,
            flag=HIDDEN_ACCUM_FLAG,
            volume_ratio=ratio,
            compressed=compressed,
            upward=upward,
            aggressive_buy=aggressive,
            flow_spike=flow_spike,
            resistance_break=breakout,
            hidden_accumulation=True,
            supported=supported,
            reasons=tuple(reasons),
            score=score,
        )
    if watch:
        reasons.insert(0, WATCH_FLAG)
        score = Decimal("5.0") + min((ratio or _ONE) - VOLUME_SURGE_RATIO, Decimal("2"))
        if aggressive:
            score += Decimal("0.8")
        if flow_spike:
            score += Decimal("0.8")
        return ExplosiveDecision(
            watch=True,
            explosive=False,
            flag=WATCH_FLAG,
            volume_ratio=ratio,
            compressed=compressed,
            upward=upward,
            aggressive_buy=aggressive,
            flow_spike=flow_spike,
            resistance_break=breakout,
            hidden_accumulation=False,
            supported=supported,
            reasons=tuple(reasons),
            score=score,
        )
    if not volume_ok:
        reasons.append("لا يوجد ارتفاع حجم يتجاوز 150% من المتوسط")
    elif not (compressed or upward or supported):
        reasons.append("المدى السعري غير مضغوط والحركة ليست صاعدة ولا ممسوكة عند الدعم")
    return ExplosiveDecision(
        watch=False,
        explosive=False,
        flag=None,
        volume_ratio=ratio,
        compressed=compressed,
        upward=upward,
        aggressive_buy=aggressive,
        flow_spike=flow_spike,
        resistance_break=breakout,
        hidden_accumulation=False,
        supported=supported,
        reasons=tuple(reasons),
    )


def inputs_from_snapshot(row: Mapping[str, Any]) -> ExplosiveInputs | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    volumes = row.get("window_volumes") or row.get("volumes") or row.get("prior_volumes") or ()
    closes = row.get("prior_closes") or row.get("closes") or ()
    if isinstance(closes, (list, tuple)) and len(closes) > 1:
        last_close = _positive(closes[-1])
        price = _positive(row.get("last_price") or row.get("price") or row.get("close_price"))
        if last_close is not None and price is not None and last_close == price:
            if isinstance(volumes, (list, tuple)) and len(volumes) == len(closes):
                volumes = volumes[:-1]
            closes = closes[:-1]
        elif last_close is not None and price is None:
            closes = closes[:-1]
    return ExplosiveInputs(
        symbol=symbol,
        name=str(row.get("name") or ""),
        price=_positive(row.get("last_price") or row.get("price") or row.get("close_price")),
        volume=_positive(row.get("session_volume") or row.get("volume")),
        window_volumes=tuple(volumes) if not isinstance(volumes, tuple) else volumes,
        minute_volume_ratio=_positive(row.get("minute_volume_ratio") or row.get("volume_ratio")),
        session_high=_positive(row.get("session_high") or row.get("high")),
        session_low=_positive(row.get("session_low") or row.get("low")),
        prev_close=_positive(row.get("prev_close")),
        session_open=_positive(row.get("session_open") or row.get("open")),
        change_percent=_as_decimal(row.get("change_percent")),
        net_flow=_as_decimal(row.get("net_flow")),
        inflow=_as_decimal(row.get("inflow")),
        outflow=_as_decimal(row.get("outflow")),
        buy_volume=_as_decimal(row.get("buy_volume")),
        sell_volume=_as_decimal(row.get("sell_volume")),
        last_side=_side(row.get("last_side") or row.get("side")),
        bid=_positive(row.get("bid")),
        ask=_positive(row.get("ask")),
        prior_closes=tuple(closes) if not isinstance(closes, tuple) else closes,
        support=_positive(row.get("support") or row.get("swing_low")),
        bid_wall_price=_wall_price(row.get("bid_wall")),
        near_bid_wall=bool(row.get("near_bid_wall")),
        clustered_buys=_int(row.get("clustered_buys")),
        institutional_mfi=_as_decimal(row.get("institutional_mfi")),
        trap_kind=_trap_kind(row.get("trap") or row.get("trap_kind")),
    )


def _volume_ratio(inputs: ExplosiveInputs) -> Decimal | None:
    current = _positive(inputs.volume)
    baseline = volume_profile_average(inputs.window_volumes, window=VOLUME_WINDOW)
    session_ratio = None
    if current is not None and baseline is not None and baseline > 0:
        session_ratio = current / baseline
    minute = _positive(inputs.minute_volume_ratio)
    if session_ratio is None:
        return minute
    if minute is None:
        return session_ratio
    return max(session_ratio, minute)


def _range_compressed(inputs: ExplosiveInputs) -> bool:
    price = _positive(inputs.price)
    high = _positive(inputs.session_high)
    low = _positive(inputs.session_low)
    if price and high and low and high >= low:
        span = (high - low) / price
        if span <= COMPRESSED_RANGE_PCT:
            return True
    change = _as_decimal(inputs.change_percent)
    if change is not None and abs(change) <= COMPRESSED_CHANGE_PCT:
        return True
    return False


def _held_at_support(inputs: ExplosiveInputs) -> bool:
    """True when last trades are parked on the bid wall / session low (iceberg absorption)."""

    if inputs.near_bid_wall:
        return True
    price = _positive(inputs.price)
    if price is None:
        return False
    floors = [
        value
        for value in (
            _positive(inputs.support),
            _positive(inputs.bid_wall_price),
            _positive(inputs.session_low),
        )
        if value is not None
    ]
    if not floors:
        return False
    floor = min(floors)
    if floor <= 0:
        return False
    band = max(floor * SUPPORT_BAND, price * SUPPORT_BAND)
    return abs(price - floor) <= band


def _upward_tape(inputs: ExplosiveInputs) -> bool:
    price = _positive(inputs.price)
    prev = _positive(inputs.prev_close)
    opened = _positive(inputs.session_open)
    change = _as_decimal(inputs.change_percent)
    if change is not None and change >= 0:
        return True
    if price is not None and prev is not None and price >= prev:
        return True
    if price is not None and opened is not None and price >= opened:
        return True
    return False


def _dumping(inputs: ExplosiveInputs) -> bool:
    change = _as_decimal(inputs.change_percent)
    net = _as_decimal(inputs.net_flow)
    sell_heavy = aggressive_buy_confirmed(inputs.buy_volume, inputs.sell_volume) is False
    if change is not None and change <= DUMP_CHANGE_PCT and not _range_compressed(inputs):
        return True
    if net is not None and net < 0 and sell_heavy:
        return True
    return False


def _aggressive_ask_flow(inputs: ExplosiveInputs) -> bool:
    confirmed = aggressive_buy_confirmed(
        inputs.buy_volume,
        inputs.sell_volume,
        min_ratio=MIN_AGGRESSIVE_BUY,
    )
    if confirmed:
        return True
    inflow = _as_decimal(inputs.inflow)
    outflow = _as_decimal(inputs.outflow)
    money = aggressive_buy_confirmed(inflow, outflow, min_ratio=MIN_AGGRESSIVE_BUY)
    if money:
        return True
    side = _side(inputs.last_side)
    price = _positive(inputs.price)
    ask = _positive(inputs.ask)
    if side == TradeSide.BUY.value and price is not None and ask is not None and price >= ask * Decimal("0.999"):
        return True
    return False


def _net_flow_spike(inputs: ExplosiveInputs) -> bool:
    net = _as_decimal(inputs.net_flow)
    inflow = _as_decimal(inputs.inflow) or _ZERO
    outflow = _as_decimal(inputs.outflow) or _ZERO
    if net is None and (inflow or outflow):
        net = inflow - outflow
    if net is None or net <= 0:
        return False
    if inflow > 0 and outflow > 0:
        return inflow >= outflow * Decimal("1.15")
    return True


def _local_resistance(closes: Iterable[Any] | None) -> Decimal | None:
    sample: list[Decimal] = []
    for raw in closes or []:
        value = _positive(raw)
        if value is not None:
            sample.append(value)
    if not sample:
        return None
    window = sample[-max(1, VOLUME_WINDOW) :]
    return max(window)


def _breaks_resistance(price: Decimal | None, resistance: Decimal | None) -> bool:
    last = _positive(price)
    if last is None or resistance is None or resistance <= 0:
        return False
    return last >= resistance * BREAKOUT_MARGIN


def _side(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, TradeSide):
        return value.value
    text = str(value).strip().upper()
    if text in {TradeSide.BUY.value, "BUY", "ASK", "UP"}:
        return TradeSide.BUY.value
    if text in {TradeSide.SELL.value, "SELL", "BID", "DOWN"}:
        return TradeSide.SELL.value
    return None


def _positive(value: Any) -> Decimal | None:
    number = _as_decimal(value)
    if number is None or number <= 0:
        return None
    return number


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _wall_price(wall: Any) -> Decimal | None:
    if isinstance(wall, dict):
        return _positive(wall.get("price"))
    return _positive(wall)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _trap_kind(value: Any) -> str | None:
    if isinstance(value, dict):
        kind = str(value.get("kind") or "").strip()
        return kind or None
    text = str(value or "").strip()
    return text or None
