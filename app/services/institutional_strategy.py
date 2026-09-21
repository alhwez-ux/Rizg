"""SMC-inspired accumulation, volume confirmation, and long-plan safety."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Sequence

VOLUME_WINDOW = 10
MIN_VOLUME_MULTIPLE = Decimal("1.5")
MIN_AGGRESSIVE_BUY = Decimal("0.55")
MIN_REWARD_RATIO = Decimal("1.3")
MIN_CLUSTER_BARS = 2
SUPPORT_BAND = Decimal("0.008")


def volume_profile_average(volumes: Iterable[Any] | None, *, window: int = VOLUME_WINDOW) -> Decimal | None:
    """Mean of the last `window` positive volume prints (typically 10 sessions)."""

    sample: list[Decimal] = []
    for raw in volumes or []:
        try:
            value = Decimal(str(raw))
        except (ArithmeticError, TypeError, ValueError):
            continue
        if value.is_finite() and value > 0:
            sample.append(value)
    if not sample:
        return None
    recent = sample[-max(1, window) :]
    return sum(recent, Decimal("0")) / Decimal(len(recent))


def aggressive_buy_confirmed(
    buy_volume: Any = None,
    sell_volume: Any = None,
    *,
    min_ratio: Decimal = MIN_AGGRESSIVE_BUY,
) -> bool | None:
    """True when aggressive buys dominate; None when the tape has no buy/sell split."""

    buy = _positive(buy_volume)
    sell = _positive(sell_volume)
    if buy is None and sell is None:
        return None
    buy = buy or Decimal("0")
    sell = sell or Decimal("0")
    total = buy + sell
    if total <= 0:
        return None
    return (buy / total) >= min_ratio


def volume_confirms_entry(
    volume: Any,
    window_volumes: Iterable[Any] | None = None,
    *,
    buy_volume: Any = None,
    sell_volume: Any = None,
    tape_ratio: Any = None,
    min_multiple: Decimal = MIN_VOLUME_MULTIPLE,
) -> bool:
    """Reject fake breakouts: current volume must dominate the 10-session profile.

    Aggressive buying (buy volume > sell volume) is required when that split exists.
    """

    current = _positive(volume)
    avg = volume_profile_average(window_volumes)
    ratio = _positive(tape_ratio)
    confirmed = False
    if current is not None and avg is not None and avg > 0:
        confirmed = current >= avg * min_multiple
    elif ratio is not None:
        confirmed = ratio >= min_multiple
    if not confirmed:
        return False
    aggression = aggressive_buy_confirmed(buy_volume, sell_volume)
    if aggression is False:
        return False
    return True


def hidden_accumulation_from_candles(
    lows: Sequence[Any] | None,
    volumes: Sequence[Any] | None,
    *,
    closes: Sequence[Any] | None = None,
    lookback: int = VOLUME_WINDOW,
) -> bool:
    """Clustered large-volume bars printed near the swing low *before* the break."""

    if lows is None or volumes is None:
        return False
    size = min(len(lows), len(volumes))
    if closes is not None:
        size = min(size, len(closes))
    if size < max(6, lookback // 2):
        return False
    start = max(0, size - lookback - 1)
    end = size - 1  # exclude the putative breakout bar
    window_lows = [_positive(lows[index]) for index in range(start, end)]
    window_vols = [_positive(volumes[index]) for index in range(start, end)]
    support = min((value for value in window_lows if value is not None), default=None)
    avg = volume_profile_average(value for value in window_vols if value is not None)
    if support is None or avg is None or avg <= 0:
        return False
    band = support * SUPPORT_BAND
    clustered = 0
    for low, volume in zip(window_lows, window_vols):
        if low is None or volume is None:
            continue
        if low <= support + band and volume >= avg * Decimal("1.8"):
            clustered += 1
    if clustered < MIN_CLUSTER_BARS:
        return False
    if closes is None or size < 2:
        return True
    last = _positive(closes[-1])
    prior = _positive(closes[-2])
    if last is None:
        return True
    # Still a *setup*: last close has not already extended far above the cluster.
    if last > support * Decimal("1.03"):
        return False
    if prior is not None and last < prior:
        return False
    return True


def structural_swing_low(
    lows: Iterable[Any] | None,
    *,
    fallback: Any = None,
    window: int = VOLUME_WINDOW,
) -> Decimal | None:
    sample: list[Decimal] = []
    for raw in lows or []:
        value = _positive(raw)
        if value is not None:
            sample.append(value)
    if sample:
        return min(sample[-max(1, window) :])
    return _positive(fallback)


def reward_ratio(entry: Any, target: Any, stop: Any) -> Decimal | None:
    price = _positive(entry)
    tgt = _positive(target)
    sl = _positive(stop)
    if price is None or tgt is None or sl is None:
        return None
    risk = price - sl
    if risk <= 0:
        return None
    return (tgt - price) / risk


def _positive(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return number
