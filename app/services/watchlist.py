from __future__ import annotations

import json
import threading
from pathlib import Path

from app.core.exceptions import InvalidSymbolError, WatchlistFullError
from app.models.screener import normalize_tasi_symbol

_DEFAULT_PATH = Path("data/watchlist.json")
_DEFAULT_SYMBOLS = ("4030",)


class WatchlistService:
    """Persisted custom TASI watchlist for the liquidity screener."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        initial: list[str] | None = None,
        max_symbols: int = 20,
    ) -> None:
        self._path = path or _DEFAULT_PATH
        self._max = max_symbols
        self._guard = threading.RLock()
        self._symbols: list[str] = []
        seed = initial if initial is not None else list(_DEFAULT_SYMBOLS)
        self._load(seed)

    def symbols(self) -> list[str]:
        with self._guard:
            return list(self._symbols)

    def contains(self, symbol: str) -> bool:
        return symbol.upper() in set(self.symbols())

    def add(self, raw_symbol: str) -> list[str]:
        try:
            ticker = normalize_tasi_symbol(raw_symbol)
        except ValueError as exc:
            raise InvalidSymbolError(raw_symbol) from exc
        with self._guard:
            if ticker not in self._symbols:
                if len(self._symbols) >= self._max:
                    raise WatchlistFullError(self._max)
                self._symbols.append(ticker)
                self._save()
            return list(self._symbols)

    def remove(self, raw_symbol: str) -> list[str]:
        try:
            ticker = normalize_tasi_symbol(raw_symbol)
        except ValueError as exc:
            raise InvalidSymbolError(raw_symbol) from exc
        with self._guard:
            self._symbols = [item for item in self._symbols if item != ticker]
            if not self._symbols:
                self._symbols = ["4030"]
            self._save()
            return list(self._symbols)

    def _load(self, seed: list[str]) -> None:
        loaded: list[str] = []
        if self._path.exists():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                raw_items = payload.get("symbols", payload) if isinstance(payload, dict) else payload
                if isinstance(raw_items, list):
                    for item in raw_items:
                        try:
                            loaded.append(normalize_tasi_symbol(str(item)))
                        except ValueError:
                            continue
            except (OSError, json.JSONDecodeError):
                loaded = []
        if not loaded:
            for item in seed:
                try:
                    loaded.append(normalize_tasi_symbol(str(item)))
                except ValueError:
                    continue
        if not loaded:
            loaded = list(_DEFAULT_SYMBOLS)
        seen: set[str] = set()
        unique: list[str] = []
        for item in loaded:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        self._symbols = unique[: self._max]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"symbols": self._symbols}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
