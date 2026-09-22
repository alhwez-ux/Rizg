from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Callable, Iterable

from app.services.liquidity_engine import MarketLevels

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HALF = Decimal("0.50")
_RATIO_Q = Decimal("0.0001")
_SCORE_Q = Decimal("0.01")
_PRICE_Q = Decimal("0.01")
_DEFAULT_ENTRY_SHARE = Decimal("0.15")
_EXIT_SELL_FLOOR = Decimal("0.55")
_VOLUME_EXHAUST = Decimal("0.80")
_QUIET_CLEAR_HITS = 3


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
    session_value: Decimal | None = None
    vwap: Decimal | None = None
    atr: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    book_pressure: Decimal | None = None
    avg_volume: Decimal | None = None
    swing_low: Decimal | None = None
    in_gainers: bool = False
    in_volume_leaders: bool = False
    in_value_leaders: bool = False
    tracked: bool = False
    symbol: str | None = None


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


@dataclass
class _SymbolLatch:
    entry_streak: int = 0
    exit_streak: int = 0
    quiet_streak: int = 0
    last_sample_at: float = 0.0
    last_entry_at: float = 0.0
    last_exit_at: float = 0.0
    published: str = ""


class SignalEngine:
    """Day-trade entry/exit from persistent net money flow + buy pressure.

    EMA/RSI never gate a badge. A raw candidate still needs a multi-check
    confirmation window so a single spike does not flicker دخول/خروج.
    Exit requires a confirmed reversal or volume exhaustion, not a flat tape.
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
        entry_share: Decimal = _DEFAULT_ENTRY_SHARE,
        confirm_hits: int = 1,
        exit_confirm_hits: int = 1,
        sample_seconds: float = 0,
        entry_cooldown_seconds: float = 0,
        exit_cooldown_seconds: float = 0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._net_threshold = net_flow_threshold
        self._aggressive = aggressive_ratio
        self._volume_surge = volume_surge
        self._atr_target = atr_target_mult
        self._atr_stop = atr_stop_mult
        self._book_threshold = book_pressure_threshold
        self._exit_ceiling = exit_net_ceiling
        self._entry_share = entry_share if entry_share > 0 else _DEFAULT_ENTRY_SHARE
        self._confirm_hits = max(1, int(confirm_hits))
        self._exit_confirm_hits = max(1, int(exit_confirm_hits))
        self._sample_seconds = max(0.0, float(sample_seconds))
        self._entry_cooldown = max(0.0, float(entry_cooldown_seconds))
        self._exit_cooldown = max(0.0, float(exit_cooldown_seconds))
        self._clock = clock or time.monotonic
        self._latches: dict[str, _SymbolLatch] = {}

    @property
    def confirm_hits(self) -> int:
        return self._confirm_hits

    def reset(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._latches.clear()
            return
        self._latches.pop(str(symbol).strip().upper(), None)

    def evaluate(
        self,
        inputs: SignalInputs,
        *,
        peer_nets: Iterable[Decimal | float | int | None] | None = None,
    ) -> SignalDecision:
        reasons: list[str] = []
        score = _ZERO

        inflow, outflow, net, proxied = _resolved_flow(inputs)
        buy_ratio, sell_ratio, pressure_source = _pressure_ratios(inputs, inflow, outflow)
        profile = _positive(inputs.avg_volume) or inputs.prev_volume
        surge = _volume_surge(inputs.volume, profile)
        book_pressure = inputs.book_pressure
        if book_pressure is None:
            book_pressure = _ratio(inputs.bid_size, inputs.ask_size)
        flow_verified = (not proxied) and net is not None and (buy_ratio is not None or sell_ratio is not None)

        if proxied and net is not None and net != _ZERO:
            reasons.append("صافي تدفق تقديري من اتجاه السعر × قيمة التداول")
        if net is not None:
            if net > 0:
                reasons.append("صافي تدفق أموال موجب")
                score += Decimal("2.0") + min(abs(net) / max(self._net_threshold, _ONE), Decimal("3"))
            elif net < 0:
                reasons.append("صافي تدفق أموال سالب")
                score += Decimal("1.2") + min(abs(net) / max(self._net_threshold, _ONE), Decimal("3"))

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
        book_buy = book_pressure is not None and book_pressure >= self._book_threshold
        volume_spike = surge is not None and surge >= self._volume_surge
        buying_spike = aggressive_buy or book_buy or volume_spike
        not_selling = buy_ratio is None or buy_ratio >= _HALF
        tape_ready = _has_tape(inputs, inflow=inflow, outflow=outflow, net=net)
        cutoff = positive_net_cutoff(peer_nets, share=self._entry_share) if peer_nets is not None else None
        relative_hit = bool(cutoff is not None and net is not None and net >= cutoff and not_selling)
        spike_hit = bool(net is not None and net > 0 and buying_spike and not_selling)
        absolute_hit = bool(
            (not proxied)
            and net is not None
            and net >= self._net_threshold
            and (buy_ratio is None or aggressive_buy)
        )
        volume_confirmed = surge is not None and surge >= Decimal("1.5")
        has_volume_profile = _positive(inputs.avg_volume) is not None
        raw_entry = bool(relative_hit or spike_hit or absolute_hit)
        if has_volume_profile and raw_entry and not volume_confirmed:
            reasons.append("كسر بدون تأكيد حجم مقابل متوسط 10 جلسات — احتمال اختراق وهمي")
            raw_entry = False
        raw_exit = _raw_exit(
            net=net,
            tape_ready=tape_ready,
            raw_entry=raw_entry,
            sell_ratio=sell_ratio,
            book_pressure=book_pressure,
            surge=surge,
            exit_ceiling=self._exit_ceiling,
            net_threshold=self._net_threshold,
            aggressive=self._aggressive,
            book_threshold=self._book_threshold,
        )
        entry, exit_signal = self._stabilize(
            inputs.symbol,
            raw_entry=raw_entry,
            raw_exit=raw_exit,
            reasons=reasons,
        )
        if raw_exit:
            reasons.append("انعكاس زخم أو استنزاف سيولة وليس ضجيجاً لحظياً")
        if relative_hit:
            pct = int(self._entry_share * 100)
            reasons.append(f"ضمن أعلى {pct}% من صافي التدفق الموجب بين الأقران")
        if spike_hit and not relative_hit:
            reasons.append("ضغط شراء لحظي (كمية عدوانية أو دفتر أو ارتفاع حجم)")
        if entry and volume_confirmed:
            reasons.append("تأكيد سيولة: الكمية العدوانية أعلى من متوسط 10 جلسات")

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
        elif net is not None and net > 0 and not entry:
            reasons.append(
                f"لم يصل لعتبة الدخول النسبية (cutoff={cutoff}) ولا يوجد ضغط شراء لحظي"
            )
        elif net is not None and (buy_ratio is None and sell_ratio is None):
            reasons.append("لا توجد بيانات كمية/قيمة كافية لتأكيد الضغط العدواني")
        elif not tape_ready:
            reasons.append("بانتظار تدفق سيولة موثّق (صافي + شراء/بيع)")

        _log_entry_decision(
            inputs,
            net=net,
            buy_ratio=buy_ratio,
            book_pressure=book_pressure,
            surge=surge,
            cutoff=cutoff,
            proxied=proxied,
            relative_hit=relative_hit,
            spike_hit=spike_hit,
            absolute_hit=absolute_hit,
            entry=entry,
            exit_signal=exit_signal,
            reasons=reasons,
        )

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

    def _stabilize(
        self,
        symbol: str | None,
        *,
        raw_entry: bool,
        raw_exit: bool,
        reasons: list[str],
    ) -> tuple[bool, bool]:
        ticker = str(symbol or "").strip().upper()
        latch_on = (
            self._confirm_hits > 1
            or self._exit_confirm_hits > 1
            or self._sample_seconds > 0
            or self._entry_cooldown > 0
            or self._exit_cooldown > 0
        )
        if not ticker or not latch_on:
            return raw_entry, raw_exit

        now = float(self._clock())
        state = self._latches.setdefault(ticker, _SymbolLatch())
        if state.last_sample_at and (now - state.last_sample_at) < self._sample_seconds:
            return state.published == "entry", state.published == "exit"

        state.last_sample_at = now
        if raw_entry:
            state.entry_streak += 1
            state.exit_streak = 0
            state.quiet_streak = 0
        elif raw_exit:
            state.exit_streak += 1
            state.entry_streak = 0
            state.quiet_streak = 0
        else:
            state.entry_streak = 0
            state.exit_streak = 0
            state.quiet_streak += 1

        entry_ready = raw_entry and state.entry_streak >= self._confirm_hits
        exit_ready = raw_exit and state.exit_streak >= self._exit_confirm_hits
        if raw_entry and not entry_ready:
            reasons.append(f"بانتظار تأكيد الدخول ({state.entry_streak}/{self._confirm_hits})")
        if raw_exit and not exit_ready:
            reasons.append(f"بانتظار تأكيد الخروج ({state.exit_streak}/{self._exit_confirm_hits})")

        if entry_ready:
            if state.published != "entry" and state.last_entry_at and (now - state.last_entry_at) < self._entry_cooldown:
                reasons.append("تهدئة بعد إشارة دخول سابقة — تجاهل التكرار")
                state.entry_streak = 0
                return False, False
            if state.published != "entry":
                state.last_entry_at = now
            state.published = "entry"
            return True, False

        if exit_ready:
            if state.published != "exit" and state.last_exit_at and (now - state.last_exit_at) < self._exit_cooldown:
                reasons.append("تهدئة بعد إشارة خروج سابقة — تجاهل التكرار")
                state.exit_streak = 0
                return False, False
            if state.published != "exit":
                state.last_exit_at = now
            state.published = "exit"
            return False, True

        if state.published == "entry":
            reasons.append("المحافظة على الدخول حتى تأكيد انعكاس الزخم أو استنزاف السيولة")
            return True, False
        if state.published == "exit" and state.quiet_streak < _QUIET_CLEAR_HITS:
            return False, True
        if state.quiet_streak >= _QUIET_CLEAR_HITS:
            state.published = ""
        return False, False


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
        if suggested_entry is not None:
            target, stop = long_trade_levels(
                suggested_entry,
                atr=atr,
                target_mult=atr_target_mult,
                stop_mult=atr_stop_mult,
                swing_low=inputs.swing_low,
            )
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


def long_trade_levels(
    entry: Decimal | float | int | str,
    *,
    atr: Decimal | float | int | str | None = None,
    target_mult: Decimal | float = Decimal("1.5"),
    stop_mult: Decimal | float = Decimal("1.0"),
    swing_low: Decimal | float | int | str | None = None,
    min_reward: Decimal | float | None = Decimal("1.3"),
) -> tuple[Decimal, Decimal]:
    """Long/BUY geometry: target is strictly above entry, stop strictly below.

    Target sits Entry + 1.5%–3% (volatility-scaled, ATR-aware). Stop sits below
    the structural swing low when available, otherwise Entry − ATR. Operators
    are never inverted.
    """

    price = _as_decimal(entry)
    if price is None or price <= _ZERO:
        raise ValueError("long entry price must be positive")
    span = _as_decimal(atr)
    if span is None or span <= _ZERO:
        span = price * Decimal("0.012")
    t_mult = _as_decimal(target_mult) or Decimal("1.5")
    s_mult = _as_decimal(stop_mult) or Decimal("1.0")
    if t_mult <= _ZERO:
        t_mult = Decimal("1.5")
    if s_mult <= _ZERO:
        s_mult = Decimal("1.0")
    volatility = span / price
    if volatility <= Decimal("0.01"):
        target_pct = Decimal("0.015")
    elif volatility >= Decimal("0.03"):
        target_pct = Decimal("0.03")
    else:
        target_pct = Decimal("0.015") + (volatility - Decimal("0.01")) * Decimal("0.75")
    # Long only: add for target, subtract for stop.
    target = price + max(span * t_mult, price * target_pct)
    stop = price - max(span * s_mult, price * Decimal("0.008"))
    floor = _as_decimal(swing_low)
    if floor is not None and _ZERO < floor < price:
        structural = floor * Decimal("0.995")
        near = (price - structural) <= max(span * Decimal("2"), price * Decimal("0.025"))
        if near and _ZERO < structural < price:
            stop = min(stop, structural)
    if stop <= _ZERO:
        stop = price * Decimal("0.98")
    if stop >= price:
        stop = price * Decimal("0.985")
    if target <= price:
        target = price * (Decimal("1") + target_pct)
    reward_floor = _as_decimal(min_reward)
    risk = price - stop
    if reward_floor is not None and reward_floor > _ZERO and risk > 0:
        needed = price + reward_floor * risk
        if target < needed:
            target = min(needed, max(target, price * Decimal("1.08")))
    if target <= price:
        target = price * Decimal("1.015")
    if not (target > price > stop > _ZERO):
        target = price * Decimal("1.02")
        stop = price * Decimal("0.985")
    return target, stop


def is_valid_long_plan(entry: Any, target: Any, stop: Any) -> bool:
    """True only when target > entry > stop > 0 for a long recommendation."""

    price = _as_decimal(entry)
    target_price = _as_decimal(target)
    stop_price = _as_decimal(stop)
    return (
        price is not None
        and target_price is not None
        and stop_price is not None
        and target_price > price > stop_price > _ZERO
    )


def keep_long_recommendations(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop any recommendation whose long target/stop geometry is inverted or missing."""

    kept: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        entry = row.get("entry_price") or row.get("close_price")
        if is_valid_long_plan(entry, row.get("target_price"), row.get("stop_loss")):
            kept.append(row)
            continue
        logger.warning(
            "[entry-scan] dropped inverted long plan %s entry=%s target=%s stop=%s",
            row.get("symbol"),
            entry,
            row.get("target_price"),
            row.get("stop_loss"),
        )
    return kept


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
        session_value=inputs.session_value,
        vwap=inputs.vwap or levels.vwap,
        atr=inputs.atr or levels.atr,
        bid=inputs.bid or levels.bid,
        ask=inputs.ask or levels.ask,
        bid_size=inputs.bid_size or levels.bid_size,
        ask_size=inputs.ask_size or levels.ask_size,
        book_pressure=inputs.book_pressure or levels.book_pressure,
        avg_volume=inputs.avg_volume,
        swing_low=inputs.swing_low or getattr(levels, "session_low", None) or getattr(levels, "low", None),
        in_gainers=inputs.in_gainers,
        in_volume_leaders=inputs.in_volume_leaders,
        in_value_leaders=inputs.in_value_leaders,
        tracked=inputs.tracked,
        symbol=inputs.symbol,
    )


def signal_engine_from_settings(settings: Any, *, clock: Callable[[], float] | None = None) -> SignalEngine:
    """Build a SignalEngine with the production confirmation / cooldown settings."""

    share = getattr(settings, "signal_entry_share", Decimal("0.15"))
    try:
        entry_share = Decimal(str(share))
    except (InvalidOperation, TypeError, ValueError):
        entry_share = Decimal("0.15")
    return SignalEngine(
        net_flow_threshold=settings.signal_net_flow_threshold,
        aggressive_ratio=settings.signal_aggressive_ratio,
        atr_target_mult=settings.signal_atr_target_mult,
        atr_stop_mult=settings.signal_atr_stop_mult,
        exit_net_ceiling=settings.signal_exit_net_ceiling,
        entry_share=entry_share,
        confirm_hits=int(getattr(settings, "signal_confirm_hits", 3) or 3),
        exit_confirm_hits=int(getattr(settings, "signal_exit_confirm_hits", 3) or 3),
        sample_seconds=float(getattr(settings, "signal_sample_seconds", 45) or 0),
        entry_cooldown_seconds=float(getattr(settings, "signal_entry_cooldown_seconds", 180) or 0),
        exit_cooldown_seconds=float(getattr(settings, "signal_exit_cooldown_seconds", 120) or 0),
        clock=clock,
    )


def _raw_exit(
    *,
    net: Decimal | None,
    tape_ready: bool,
    raw_entry: bool,
    sell_ratio: Decimal | None,
    book_pressure: Decimal | None,
    surge: Decimal | None,
    exit_ceiling: Decimal,
    net_threshold: Decimal,
    aggressive: Decimal,
    book_threshold: Decimal,
) -> bool:
    """True only on a real fade: negative net plus selling pressure or volume exhaustion."""

    if raw_entry or not tape_ready or net is None:
        return False
    floor = exit_ceiling if exit_ceiling < _ZERO else _ZERO
    if net >= floor:
        return False
    sell_floor = aggressive if aggressive >= _EXIT_SELL_FLOOR else _EXIT_SELL_FLOOR
    aggressive_sell = sell_ratio is not None and sell_ratio >= sell_floor
    book_sell = book_pressure is not None and book_pressure <= (_ONE - book_threshold)
    volume_exhaust = surge is not None and surge <= _VOLUME_EXHAUST
    strong_outflow = net <= -abs(net_threshold)
    return bool(aggressive_sell or book_sell or volume_exhaust or strong_outflow)


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


def positive_net_cutoff(
    nets: Iterable[Decimal | float | int | None] | None,
    *,
    share: Decimal = _DEFAULT_ENTRY_SHARE,
) -> Decimal | None:
    """Minimum net flow that still sits in the top `share` of positive peers."""

    if nets is None:
        return None
    positive: list[Decimal] = []
    for raw in nets:
        number = _as_decimal(raw)
        if number is not None and number > 0:
            positive.append(number)
    if not positive:
        return None
    keep = max(1, math.ceil(len(positive) * float(share if share > 0 else _DEFAULT_ENTRY_SHARE)))
    positive.sort()
    return positive[-keep]


def _resolved_flow(
    inputs: SignalInputs,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, bool]:
    inflow = inputs.inflow
    outflow = inputs.outflow
    net = inputs.net_flow
    if net is None and inflow is not None and outflow is not None:
        net = inflow - outflow
    tape = _has_tape(inputs, inflow=inflow, outflow=outflow, net=net)
    if tape and net not in (None, _ZERO):
        return inflow, outflow, net, False
    proxy = _proxy_net(inputs)
    if proxy is not None and (net is None or net == _ZERO):
        return inflow, outflow, proxy, True
    if inflow is None and outflow is None and net is None:
        return None, None, None, False
    return inflow, outflow, net, False


def _proxy_net(inputs: SignalInputs) -> Decimal | None:
    """Direction × traded value when the tick tape has not classified buys/sells yet."""

    change = inputs.change_percent
    if change is None or change == _ZERO:
        return None
    value = _positive(inputs.session_value)
    if value is None:
        price = _positive(inputs.price)
        if price is not None and inputs.volume is not None and inputs.volume > 0:
            value = price * inputs.volume
    if value is None:
        return None
    return (value * change) / Decimal("100")


def _as_decimal(value: Decimal | float | int | str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _log_entry_decision(
    inputs: SignalInputs,
    *,
    net: Decimal | None,
    buy_ratio: Decimal | None,
    book_pressure: Decimal | None,
    surge: Decimal | None,
    cutoff: Decimal | None,
    proxied: bool,
    relative_hit: bool,
    spike_hit: bool,
    absolute_hit: bool,
    entry: bool,
    exit_signal: bool,
    reasons: list[str],
) -> None:
    ticker = (inputs.symbol or "").strip().upper() or "-"
    outcome = "ENTRY" if entry else "EXIT" if exit_signal else "SKIP"
    if outcome == "SKIP" and (net is None or net <= 0):
        logger.debug(
            "[entry-scan] %s net=%s -> SKIP | %s",
            ticker,
            net,
            "; ".join(reasons[:3]) or "no-reasons",
        )
        return
    logger.info(
        "[entry-scan] %s net=%s buy_ratio=%s book=%s surge=%s cutoff=%s proxied=%s relative=%s spike=%s absolute=%s -> %s | %s",
        ticker,
        net,
        buy_ratio,
        book_pressure,
        surge,
        cutoff,
        proxied,
        relative_hit,
        spike_hit,
        absolute_hit,
        outcome,
        "; ".join(reasons[:4]) or "no-reasons",
    )


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
