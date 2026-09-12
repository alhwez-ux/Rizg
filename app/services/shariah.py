from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CANDIDATES = (
    _ROOT / "web" / "prisma" / "tasi-universe.json",
    _ROOT / "data" / "tasi_compliance.json",
)


@lru_cache(maxsize=1)
def compliance_universe() -> tuple[dict[str, object], ...]:
    for path in _CANDIDATES:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            return tuple(item for item in payload if isinstance(item, dict))
    return ()


def prohibited_symbols() -> set[str]:
    return {
        str(item["symbol"]).strip().upper()
        for item in compliance_universe()
        if str(item.get("currentStatus") or "").upper() == "PROHIBITED" and item.get("symbol")
    }


def is_prohibited(symbol: str) -> bool:
    ticker = (symbol or "").strip().upper()
    return bool(ticker) and ticker in prohibited_symbols()
