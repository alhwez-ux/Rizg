from __future__ import annotations

import json
import threading
from pathlib import Path

from app.models.screener import normalize_tasi_symbol
from app.services.shariah import is_prohibited

_DEFAULT_PATH = Path("data/followed.json")
_MAX_SYMBOLS = 40


class FollowedCompanies:
    """The single user's radar follow-list, shared by every device."""

    def __init__(self, path: Path | None = None, *, max_symbols: int = _MAX_SYMBOLS) -> None:
        self._path = path or _DEFAULT_PATH
        self._max = max_symbols
        self._guard = threading.RLock()
        self._saved = False
        self._companies: list[dict[str, str]] = []
        self._load()

    def snapshot(self) -> dict[str, object]:
        with self._guard:
            return {"saved": self._saved, "companies": [dict(item) for item in self._companies]}

    def replace(self, companies: list[dict[str, str]]) -> dict[str, object]:
        cleaned = _clean(companies, self._max)
        with self._guard:
            self._companies = cleaned
            self._saved = True
            self._save()
            return {"saved": True, "companies": [dict(item) for item in self._companies]}

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        raw = payload.get("companies") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            return
        self._companies = _clean(raw, self._max)
        self._saved = True

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"saved": True, "companies": self._companies}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _clean(companies: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in companies:
        if not isinstance(item, dict):
            continue
        try:
            symbol = normalize_tasi_symbol(str(item.get("symbol") or ""))
        except ValueError:
            continue
        if is_prohibited(symbol) or symbol in seen:
            continue
        seen.add(symbol)
        name = str(item.get("name") or item.get("symbolName") or "").strip()
        cleaned.append({"symbol": symbol, "name": name or symbol})
        if len(cleaned) >= limit:
            break
    return cleaned
