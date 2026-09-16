from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN

from app.services.liquidity_engine import MarketLevels

_ZERO = Decimal("0")
_ONE = Decimal("1")
_RATIO_Q = Decimal("0.0001")
_SCORE_Q = Decimal("0.01")
_PRICE_Q = Decimal("0.01")


@dataclass(frozen=True)
class SignalInputs:
    """Money-flow inputs for entry/exit. Price % is display-only and never fires a badge."""

    volume: Decimal = _ZERO
    prev_volume: Decimal | None = None
    inflow: Decimal | None = None
    outflow: Decimal | None = None
    net_flow: Decimal | None = None
    buy_volume: Decimal | None = None
    sell_volume: Decimal | None = None
    change_percent: Decimal = _ZERO
    price: Decimal | None = None
    vwap: Decimal | None = None
    atr: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    book_pressure: Decimal | None = None
    in_gainers: bool = False
    in_volume_leaders: bool = False
    in_value_leaders: bool = False
    tracked: bool = False


@dataclass(frozen=True)
class SignalDecision:
    entry: bool
    exit: bool
    unexpected: bool
    score: Decimal
    buy_ratio: Decimal | None
    sell_ratio: Decimal | None
    volume_surge: Decimal | None
    flow_verified: bool
    vwap: Decimal | None = None
    atr: Decimal | None = None
    book_pressure: Decimal | None = None
    suggested_entry: Decimal | None = None
    suggested_exit: Decimal | None = None
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)


class SignalEngine:
    """Fast day-trade entry/exit from net money flow + buy pressure.

    EMA/RSI never gate a badge. Entry fires on a modest positive net print
    with buy pressure when the split is known. Exit fires as soon as net
    flow goes flat or negative so short-term gains are not given back.
    """

    def __init__(
        self,
        *,
        net_flow_threshold: Decimal = Decimal("3000"),
        aggressive_ratio: Decimal = Decimal("0.51"),
        volume_surge: Decimal = Decimal("1.25"),
        atr_target_mult: Decimal = Decimal("1.5"),
        atr_stop_mult: Decimal = Decimal("1.0"),
        book_pressure_threshold: Decimal = Decimal("0.55"),
        exit_net_ceiling: Decimal = Decimal("0"),
    ) -> None:
        self._net_threshold = net_flow_threshold
        self._aggressive = aggressive_ratio
        self._volume_surge = volume_surge
        self._atr_target = atr_target_mult
        self._atr_stop = atr_stop_mult
        self._book_threshold = book_pressure_threshold
        self._exit_ceiling = exit_net_ceiling

    def evaluate(self, inputs: SignalInputs) -> SignalDecision:
        reasons: list[str] = []
        score = _ZERO

        inflow, outflow, net = _resolved_flow(inputs)
        buy_ratio, sell_ratio, pressure_source = _pressure_ratios(inputs, inflow, outflow)
        surge = _volume_surge(inputs.volume, inputs.prev_volume)
        book_pressure = inputs.book_pressure
        if book_pressure is None:
            book_pressure = _ratio(inputs.bid_size, inputs.ask_size)
        flow_verified = net is not None and (buy_ratio is not None or sell_ratio is not None)

        if net is not None:
            if net > 0:
                reasons.append("صافي تدفق أموال موجب")
                score += Decimal("2.0") + min(net / self._net_threshold, Decimal("3"))
            elif net < 0:
                reasons.append("صافي تدفق أموال سالب")
                score += Decimal("1.2") + min(abs(net) / self._net_threshold, Decimal("3"))

        if buy_ratio is not None and pressure_source == "volume":
            reasons.append("ضغط شراء/بيع محسوب من الكمية العدوانية")
        elif buy_ratio is not None:
            reasons.append("ضغط شراء/بيع محسوب من قيمة السيولة")

        if surge is not None and surge >= self._volume_surge:
            reasons.append("ارتفاع مفاجئ في الكمية")
            score += Decimal("0.6")

        if book_pressure is not None:
            if book_pressure >= self._book_threshold:
                reasons.append("ضغط دفتر الشراء أعلى من العرض")
                score += Decimal("0.5")
            elif book_pressure <= (_ONE - self._book_threshold):
                reasons.append("ضغط دفتر البيع أعلى من الطلب")
                score += Decimal("0.4")

        aggressive_buy = buy_ratio is not None and buy_ratio >= self._aggressive
        tape_ready = _has_tape(inputs, inflow=inflow, outflow=outflow, net=net)
        positive_flow = net is not None and net >= self._net_threshold
        # Day-trade entry: any meaningful positive net flow plus buy pressure
        # when the split is known. Missing ratios still fire on the net print.
        entry = bool(positive_flow and (buy_ratio is None or aggressive_buy))
        # Flatten / fade: lock gains as soon as net flow is flat or red.
        exit_signal = bool(
            (not entry)
            and tape_ready
            and net is not None
            and net <= self._exit_ceiling
        )

        plan = suggest_trade_plan(
            inputs,
            entry=entry,
            exit_signal=exit_signal,
            atr_target_mult=self._atr_target,
            atr_stop_mult=self._atr_stop,
        )

        if entry:
            reasons.insert(0, "إشارة دخول 🚀")
            if plan.suggested_entry is not None:
                reasons.insert(1, f"إشارة دخول بسعر مقترح: {plan.suggested_entry}")
            score += Decimal("4.0")
            if buy_ratio is not None:
                score += (buy_ratio - self._aggressive) * Decimal("4")
        elif exit_signal:
            reasons.insert(0, "إشارة خروج / تصريف ⚠️")
            if plan.suggested_exit is not None:
                reasons.insert(1, f"خروج موصى به عند: {plan.suggested_exit}")
            score += Decimal("3.5")
            if sell_ratio is not None:
                score += (sell_ratio - self._aggressive) * Decimal("4")
        elif net is not None and net > self._exit_ceiling and buy_ratio is not None and not aggressive_buy:
            reasons.append("صافي التدفق موجب لكن ضغط الشراء غير كافٍ للدخول")
        elif net is not None and (buy_ratio is None and sell_ratio is None):
            reasons.append("لا توجد بيانات كمية/قيمة كافية لتأكيد الضغط العدواني")
        elif not tape_ready:
            reasons.append("بانتظار تدفق سيولة موثّق (صافي + شراء/بيع)")

        unexpected = (not inputs.tracked) and (entry or exit_signal)
        if unexpected:
            score += Decimal("1.2")
            reasons.append("سيولة غير متتبعة على قائمة المتابعة")

        return SignalDecision(
            entry=entry,
            exit=exit_signal,
            unexpected=unexpected,
            score=score.quantize(_SCORE_Q),
            buy_ratio=None if buy_ratio is None else buy_ratio.quantize(_RATIO_Q),
            sell_ratio=None if sell_ratio is None else sell_ratio.quantize(_RATIO_Q),
            volume_surge=None if surge is None else surge.quantize(_SCORE_Q),
            flow_verified=flow_verified,
            vwap=plan.vwap,
            atr=plan.atr,
            book_pressure=None if book_pressure is None else book_pressure.quantize(_RATIO_Q),
            suggested_entry=plan.suggested_entry,
            suggested_exit=plan.suggested_exit,
            target_price=plan.target_price,
            stop_loss=plan.stop_loss,
            reasons=tuple(reasons),
        )


@dataclass(frozen=True)
class TradePlan:
    vwap: Decimal | None = None
    atr: Decimal | None = None
    suggested_entry: Decimal | None = None
    suggested_exit: Decimal | None = None
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None


def suggest_trade_plan(
    inputs: SignalInputs,
    *,
    entry: bool,
    exit_signal: bool,
    atr_target_mult: Decimal = Decimal("1.5"),
    atr_stop_mult: Decimal = Decimal("1.0"),
) -> TradePlan:
    last = _positive(inputs.price)
    vwap = _positive(inputs.vwap)
    atr = _positive(inputs.atr)
    bid = _positive(inputs.bid)
    ask = _positive(inputs.ask)
    if atr is None and last is not None:
        atr = last * Decimal("0.008")

    suggested_entry = None
    suggested_exit = None
    target = None
    stop = None

    if entry:
        suggested_entry = _entry_price(last=last, vwap=vwap, bid=bid)
        if suggested_entry is not None and atr is not None:
            target = suggested_entry + (atr * atr_target_mult)
            stop = suggested_entry - (atr * atr_stop_mult)
            if stop <= _ZERO:
                stop = suggested_entry * Decimal("0.98")
            if target <= suggested_entry:
                target = suggested_entry + atr
    if exit_signal:
        suggested_exit = _exit_price(last=last, vwap=vwap, ask=ask)

    return TradePlan(
        vwap=_price(vwap),
        atr=_price(atr, places=Decimal("0.0001")),
        suggested_entry=_price(suggested_entry),
        suggested_exit=_price(suggested_exit),
        target_price=_price(target),
        stop_loss=_price(stop),
    )


def apply_levels(inputs: SignalInputs, levels: MarketLevels | None) -> SignalInputs:
    if levels is None:
        return inputs
    return SignalInputs(
        volume=inputs.volume,
        prev_volume=inputs.prev_volume,
        inflow=inputs.inflow,
        outflow=inputs.outflow,
        net_flow=inputs.net_flow,
        buy_volume=inputs.buy_volume,
        sell_volume=inputs.sell_volume,
        change_percent=inputs.change_percent,
        price=inputs.price or levels.last_price,
        vwap=inputs.vwap or levels.vwap,
        atr=inputs.atr or levels.atr,
        bid=inputs.bid or levels.bid,
        ask=inputs.ask or levels.ask,
        bid_size=inputs.bid_size or levels.bid_size,
        ask_size=inputs.ask_size or levels.ask_size,
        book_pressure=inputs.book_pressure or levels.book_pressure,
        in_gainers=inputs.in_gainers,
        in_volume_leaders=inputs.in_volume_leaders,
        in_value_leaders=inputs.in_value_leaders,
        tracked=inputs.tracked,
    )


def _entry_price(
    *,
    last: Decimal | None,
    vwap: Decimal | None,
    bid: Decimal | None,
) -> Decimal | None:
    """Optimal bid, else VWAP pullback, else last print."""

    if last is not None and vwap is not None and last > vwap:
        pullback = vwap
        if bid is not None:
            return max(bid, pullback) if bid > vwap else pullback
        return pullback
    if bid is not None:
        return bid
    if vwap is not None:
        return vwap
    return last


def _exit_price(
    *,
    last: Decimal | None,
    vwap: Decimal | None,
    ask: Decimal | None,
) -> Decimal | None:
    """Lift the offer / VWAP, whichever is more conservative for leaving a long."""

    if ask is not None and vwap is not None:
        return max(ask, vwap)
    if ask is not None:
        return ask
    if last is not None and vwap is not None:
        return max(last, vwap)
    return last or vwap


def _has_tape(
    inputs: SignalInputs,
    *,
    inflow: Decimal | None,
    outflow: Decimal | None,
    net: Decimal | None,
) -> bool:
    if inputs.buy_volume is not None and inputs.buy_volume > 0:
        return True
    if inputs.sell_volume is not None and inputs.sell_volume > 0:
        return True
    if inflow is not None and inflow > 0:
        return True
    if outflow is not None and outflow > 0:
        return True
    return net is not None and net != _ZERO


def _resolved_flow(inputs: SignalInputs) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    inflow = inputs.inflow
    outflow = inputs.outflow
    net = inputs.net_flow
    if net is None and inflow is not None and outflow is not None:
        net = inflow - outflow
    if inflow is None and outflow is None and net is None:
        return None, None, None
    return inflow, outflow, net


def _pressure_ratios(
    inputs: SignalInputs,
    inflow: Decimal | None,
    outflow: Decimal | None,
) -> tuple[Decimal | None, Decimal | None, str | None]:
    volume_buy = _ratio(inputs.buy_volume, inputs.sell_volume)
    if volume_buy is not None:
        return volume_buy, _ONE - volume_buy, "volume"

    money_buy = _ratio(inflow, outflow)
    if money_buy is not None:
        return money_buy, _ONE - money_buy, "value"

    return None, None, None


def _ratio(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    if left < _ZERO or right < _ZERO:
        return None
    total = left + right
    if total <= 0:
        return None
    return left / total


def _volume_surge(volume: Decimal, previous: Decimal | None) -> Decimal | None:
    if previous is None or previous <= 0 or volume <= 0:
        return None
    return volume / previous


def _positive(value: Decimal | None) -> Decimal | None:
    if value is None or value <= _ZERO:
        return None
    return value


def _price(value: Decimal | None, places: Decimal = _PRICE_Q) -> Decimal | None:
    if value is None:
        return None
    step = _tick_size(value)
    quantized = (value / step).to_integral_value(rounding=ROUND_HALF_EVEN) * step
    return quantized.quantize(places)


def _tick_size(price: Decimal) -> Decimal:
    if price < Decimal("25"):
        return Decimal("0.01")
    if price < Decimal("50"):
        return Decimal("0.02")
    if price < Decimal("100"):
        return Decimal("0.05")
    return Decimal("0.10")
