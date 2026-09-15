"""Read live TASI quotes from TickerChart 1-minute FlatFiles without UI."""

from __future__ import annotations

import json
import logging
import os
import struct
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.models.screener import is_tasi_main_symbol

logger = logging.getLogger(__name__)

_RECORD = struct.Struct("<d8f")
_OLE_EPOCH = datetime(1899, 12, 30)
_CACHE_NAME = "CategoriesAndCompaniesData.json"
_map_key: tuple[str, float] | None = None
_id_to_symbol: dict[str, str] = {}


def tclive_root() -> Path:
    local = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "UniTicker" / "TCLive"
    return Path.home() / "AppData" / "Local" / "UniTicker" / "TCLive"


def collect_live_quotes(root: Path | None = None) -> list[dict[str, Any]]:
    """Return one quote payload per main-market symbol from the newest 1-minute bars."""

    base = root or tclive_root()
    mapping = load_id_to_symbol(base / "Cache" / _CACHE_NAME)
    folder = discover_minute_dir(base / "FlatFiles")
    if folder is None or not mapping:
        return []
    quotes: list[dict[str, Any]] = []
    for path in folder.glob("*.dat"):
        symbol = mapping.get(path.stem)
        if not symbol:
            continue
        bar = read_last_bar(path)
        if bar is None:
            continue
        _time, _open, _high, _low, close = bar
        if close <= 0:
            continue
        quotes.append(
            {
                "type": "quote",
                "symbol": symbol,
                "price": round(close, 4),
                "time": _time.isoformat(timespec="seconds"),
            }
        )
    quotes.sort(key=lambda item: str(item["symbol"]))
    return quotes


def discover_minute_dir(flat_root: Path) -> Path | None:
    if not flat_root.is_dir():
        return None
    best: Path | None = None
    best_score = 10_000.0
    for interval_dir in flat_root.iterdir():
        if not interval_dir.is_dir():
            continue
        sample = next(interval_dir.rglob("*.dat"), None)
        if sample is None:
            continue
        delta = bar_seconds(sample)
        if delta is None or delta <= 0:
            continue
        score = abs(delta - 60.0)
        if score < best_score:
            best_score = score
            best = sample.parent
    return best


def bar_seconds(path: Path) -> float | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < _RECORD.size * 2:
        return None
    first = _RECORD.unpack_from(data, 0)[0]
    second = _RECORD.unpack_from(data, _RECORD.size)[0]
    return abs(second - first) * 86400.0


def read_last_bar(path: Path) -> tuple[datetime, float, float, float, float] | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size < _RECORD.size:
                return None
            handle.seek(size - _RECORD.size)
            raw = handle.read(_RECORD.size)
    except OSError:
        return None
    if len(raw) != _RECORD.size:
        return None
    ole, open_, high, low, close, *_rest = _RECORD.unpack(raw)
    try:
        moment = _OLE_EPOCH + timedelta(days=float(ole))
    except (OverflowError, ValueError, OSError):
        return None
    return moment, float(open_), float(high), float(low), float(close)


def load_id_to_symbol(cache_path: Path) -> dict[str, str]:
    global _map_key, _id_to_symbol
    try:
        mtime = cache_path.stat().st_mtime
        key = (str(cache_path.resolve()), mtime)
    except OSError:
        return _id_to_symbol
    if key == _map_key and _id_to_symbol:
        return _id_to_symbol
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        logger.warning("cannot read UniTicker company cache %s", cache_path)
        return _id_to_symbol
    mapping: dict[str, str] = {}
    companies = payload.get("Companies") if isinstance(payload, dict) else payload
    if not isinstance(companies, list):
        return _id_to_symbol
    for row in companies:
        if not isinstance(row, dict):
            continue
        if str(row.get("MarketAbrv") or "").upper() != "TAD":
            continue
        ticker = str(row.get("TickerID") or "").strip()
        company_id = str(row.get("ID") or "").strip()
        if not company_id or not is_tasi_main_symbol(ticker):
            continue
        mapping[company_id] = ticker
    _id_to_symbol = mapping
    _map_key = key
    return mapping
