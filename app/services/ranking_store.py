from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path("data/company_rankings.json")


class RankingStore:
    """Persisted ranking-matrix snapshot read by the live API."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._guard = threading.RLock()
        self._rows: list[dict[str, Any]] = []
        self._synced_at: str | None = None
        self._load()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._guard:
            return [dict(row) for row in self._rows]

    def synced_at(self) -> str | None:
        with self._guard:
            return self._synced_at

    def replace(self, rows: list[dict[str, Any]], synced_at: str) -> None:
        with self._guard:
            self._rows = [dict(row) for row in rows]
            self._synced_at = synced_at
            self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            rows = payload.get("data", [])
            synced = payload.get("synced_at")
        elif isinstance(payload, list):
            rows = payload
            synced = None
        else:
            return
        if not isinstance(rows, list):
            return
        self._rows = [row for row in rows if isinstance(row, dict)]
        self._synced_at = str(synced) if synced else None

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"synced_at": self._synced_at, "data": self._rows}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
