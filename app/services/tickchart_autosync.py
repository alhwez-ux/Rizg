"""Watch TickChart desktop export folders and ingest ticks / Level-2 instantly."""

from __future__ import annotations

import os
import asyncio
import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.services.uniticker_flatfiles import collect_live_quotes

logger = logging.getLogger(__name__)

_WATCH_SUFFIXES = {".csv", ".json", ".txt", ".tsv"}
_SKIP_PREFIX = (".", "~", "$")
_SYMBOL_IN_NAME = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_DEFAULT_RELATIVE = Path("data/tickchart_live")
_HEADER_ALIASES: dict[str, frozenset[str]] = {
    "symbol": frozenset({"symbol", "ticker", "code", "sym", "الرمز", "سهم", "الشركة"}),
    "price": frozenset(
        {"price", "last", "lastprice", "lasttradeprice", "close", "cl", "السعر", "إغلاق", "الاغلاق", "اخرسعر", "آخر", "اخر"}
    ),
    "quantity": frozenset({"quantity", "qty", "volume", "size", "vol", "الحجم", "الكمية", "كمية"}),
    "time": frozenset({"time", "timestamp", "datetime", "date", "eventtime", "الوقت", "التاريخ"}),
    "side": frozenset({"side", "bs", "buysell", "نوع"}),
    "bid": frozenset({"bid", "bestbid", "طلب", "الطلب", "افضلطلب"}),
    "ask": frozenset({"ask", "bestask", "عرض", "العرض", "افضلعرض"}),
    "bid_size": frozenset({"bidsize", "bidqty", "bidquantity", "حجمالطلب", "حجمأفضلالطلب", "حجمافضلالطلب"}),
    "ask_size": frozenset({"asksize", "askqty", "askquantity", "حجمالعرض", "حجمأفضلالعرض", "حجمافضلالعرض"}),
    "value": frozenset({"value", "value_traded", "turnover", "القيمة", "القيمه"}),
    "change_percent": frozenset({"changepercent", "pchange", "التغير", "تغير"}),
    "open": frozenset({"open", "افتتاح", "إفتتاح", "الإفتتاح", "الافتتاح"}),
    "high": frozenset({"high", "أعلى", "الاعلى", "الأعلى"}),
    "low": frozenset({"low", "أدنى", "الادنى", "الأدنى"}),
    "prev_close": frozenset({"prevclose", "previousclose", "pclose", "الإغلاقالسابق", "الاغلاقالسابق"}),
    "net_flow": frozenset({"netflow", "صافيالسيولة", "صافيالسيوله"}),
    "liquidity_flow": frozenset({"liquidityflow", "تدفقالسيولة", "تدفقالسيوله"}),
    "liquidity_pct": frozenset({"liquiditypct", "نسبةالسيولة", "نسبةالسيوله"}),
    "trades": frozenset({"trades", "الصفقات"}),
}


@dataclass
class _Cursor:
    signature: tuple[int, int] = (0, 0)
    offset: int = 0
    header: list[str] = field(default_factory=list)


class TickChartAutoSync:
    """Poll TickChart export files and push prints / books into TickChartFeed."""

    def __init__(
        self,
        feed: Any,
        settings: Settings | None = None,
        *,
        watch_dirs: list[Path] | None = None,
    ) -> None:
        self._feed = feed
        self._settings = settings or get_settings()
        self._dirs = watch_dirs or discover_export_dirs(self._settings)
        self._poll = max(0.2, float(getattr(self._settings, "tickchart_export_poll_seconds", 0.5) or 0.5))
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._cursors: dict[str, _Cursor] = {}
        self._ingested = 0
        self._last_file: str | None = None
        self._last_at: str | None = None
        self._errors = 0
        self._flat_next = 0.0
        self._flat_fingerprint: tuple[int, str] | None = None

    @property
    def enabled(self) -> bool:
        return folder_watch_allowed(self._settings) and bool(self._dirs)

    @property
    def watching(self) -> bool:
        return self._running

    @property
    def connected(self) -> bool:
        return self._last_at is not None

    def status(self) -> dict[str, Any]:
        return {
            "autosync_enabled": self.enabled,
            "autosync_watching": self._running,
            "autosync_dirs": [str(path) for path in self._dirs],
            "autosync_files": self._count_files(),
            "last_file": self._last_file,
            "last_ingested": self._ingested,
            "last_sync_at": self._last_at,
        }

    async def start(self) -> None:
        if self._running or not self.enabled:
            if not self.enabled:
                logger.info("TickChart autosync is disabled")
            return
        for folder in self._dirs:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.warning("cannot create TickChart export folder %s", folder)
        self._running = True
        self._task = asyncio.create_task(self._run(), name="tickchart-autosync")
        logger.info("TickChart autosync watching %s", [str(path) for path in self._dirs])

    async def stop(self) -> None:
        self._running = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def ingest_path(self, path: Path) -> int:
        payloads = await asyncio.to_thread(parse_export_file, path)
        ingested = 0
        for payload in payloads:
            ingested += await self._feed.ingest_message(payload)
        if ingested:
            self._ingested += ingested
            self._last_file = path.name
            self._last_at = datetime.now(timezone.utc).isoformat()
            mark = getattr(self._feed, "mark_desktop_live", None)
            if callable(mark):
                mark()
        return ingested

    async def _run(self) -> None:
        while self._running:
            try:
                await self._scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._errors += 1
                logger.exception("TickChart autosync scan failed")
            await asyncio.sleep(self._poll)

    async def _scan_once(self) -> None:
        await self._scan_flatfiles()
        for path in self._iter_files():
            if not self._running:
                return
            key = str(path.resolve())
            try:
                stat = path.stat()
            except OSError:
                continue
            signature = (int(stat.st_size), int(stat.st_mtime_ns))
            cursor = self._cursors.get(key) or _Cursor()
            if cursor.signature == signature:
                continue
            grew = signature[0] > cursor.signature[0] and cursor.offset > 0
            if grew:
                payloads, new_offset = await asyncio.to_thread(_parse_append, path, cursor.offset)
            else:
                payloads = await asyncio.to_thread(parse_export_file, path)
                new_offset = signature[0]
            ingested = 0
            for payload in payloads:
                ingested += await self._feed.ingest_message(payload)
            cursor.signature = signature
            cursor.offset = new_offset
            self._cursors[key] = cursor
            if ingested:
                self._ingested += ingested
                self._last_file = path.name
                self._last_at = datetime.now(timezone.utc).isoformat()
                mark = getattr(self._feed, "mark_desktop_live", None)
                if callable(mark):
                    mark()
                logger.info("TickChart autosync ingested %s prints from %s", ingested, path.name)

    async def _scan_flatfiles(self) -> None:
        now = datetime.now(timezone.utc).timestamp()
        if now < self._flat_next:
            return
        self._flat_next = now + 10.0
        quotes = await asyncio.to_thread(collect_live_quotes)
        if not quotes:
            return
        fingerprint = tuple((item.get("symbol"), item.get("price"), item.get("time")) for item in quotes)
        if fingerprint == self._flat_fingerprint:
            return
        ingester = getattr(self._feed, "ingest_quote_snapshot", None)
        if callable(ingester):
            ingested = await ingester(quotes)
        else:
            ingested = 0
            for payload in quotes:
                ingested += await self._feed.ingest_message(payload)
        if not ingested:
            return
        self._flat_fingerprint = fingerprint
        self._ingested += ingested
        self._last_file = "uniticker_1m"
        self._last_at = datetime.now(timezone.utc).isoformat()
        mark = getattr(self._feed, "mark_desktop_live", None)
        if callable(mark):
            mark()
        logger.info("TickChart autosync ingested %s UniTicker 1m quotes", ingested)

    def _iter_files(self) -> list[Path]:
        found: list[Path] = []
        for folder in self._dirs:
            if not folder.is_dir():
                continue
            try:
                children = list(folder.iterdir())
            except OSError:
                continue
            for child in children:
                if not child.is_file():
                    continue
                if child.name.startswith(_SKIP_PREFIX):
                    continue
                if child.suffix.lower() not in _WATCH_SUFFIXES:
                    continue
                found.append(child)
        found.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0)
        return found

    def _count_files(self) -> int:
        return len(self._iter_files())


def folder_watch_allowed(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or cfg.is_production:
        return False
    if not bool(getattr(cfg, "tickchart_enabled", True)):
        return False
    return bool(getattr(cfg, "tickchart_autosync_enabled", True))


def discover_export_dirs(settings: Settings | None = None) -> list[Path]:
    cfg = settings or get_settings()
    if not folder_watch_allowed(cfg):
        return []
    found: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return
        key = str(resolved).lower()
        if key in seen:
            return
        seen.add(key)
        found.append(resolved)

    configured = str(getattr(cfg, "tickchart_export_dir", "") or "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = Path.cwd() / path
        _add(path)
    _add(Path.cwd() / "data" / "tickchart_live")
    home = Path.home()
    for candidate in (
        home / "Documents" / "TickerChart",
        home / "Documents" / "TickerChartLive",
        home / "Documents" / "TickChart",
        home / "Documents" / "LiveMetaStock",
        home / "Desktop" / "TickerChart",
        home / "Desktop" / "TickerChartLive",
        Path("C:/TickerChartLive/Export"),
        Path("C:/TickerChart/Export"),
    ):
        if candidate.is_dir():
            _add(candidate)
    for root in _uniticker_tclive_roots():
        if not root.is_dir():
            continue
        writable = _is_user_uniticker_root(root)
        export = root / "Export"
        if writable or export.is_dir():
            _add(export)
        tmp = root / "TMP"
        if tmp.is_dir():
            _add(tmp)
    return found


def _uniticker_tclive_roots() -> list[Path]:
    roots: list[Path] = []
    local = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        roots.append(Path(local) / "UniTicker" / "TCLive")
    for env_name, fallback in (
        ("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ("ProgramFiles", r"C:\Program Files"),
    ):
        base = str(os.environ.get(env_name) or fallback).strip()
        if base:
            roots.append(Path(base) / "UniTicker" / "TCLive")
    return roots


def _is_user_uniticker_root(root: Path) -> bool:
    local = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if not local:
        return False
    try:
        return root.resolve() == (Path(local) / "UniTicker" / "TCLive").resolve()
    except OSError:
        return False


def parse_export_file(path: Path) -> list[dict[str, Any]]:
    return parse_export_text(_read_text(path), path.name)


def parse_export_text(raw: str, filename: str = "") -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    hint = _symbol_from_name(filename)
    suffix = Path(filename).suffix.lower()
    if suffix == ".json" or raw.lstrip().startswith(("{", "[")):
        return _parse_json(raw, hint)
    uniticker = _parse_uniticker_grid(raw) if _is_uniticker_dump(raw) else []
    if uniticker:
        return uniticker
    return _parse_table(raw, hint)


_UNITICKER_MARKETS = frozenset({"السعودية", "saudi"})
# Columns after السوق: رمز، اسم، آخر، اتجاه، تغير، تغير%، حجم طلب، طلب، عرض، حجم عرض، حجم، قيمة، صفقات، افتتاح، أعلى، أدنى، إغلاق سابق، تدفق، صافي، نسبة
_UNITICKER_AFTER_MARKET = (
    "symbol",
    "name",
    "price",
    "direction",
    "change",
    "change_percent",
    "bid_size",
    "bid",
    "ask",
    "ask_size",
    "quantity",
    "value",
    "trades",
    "open",
    "high",
    "low",
    "prev_close",
    "liquidity_flow",
    "net_flow",
    "liquidity_pct",
)


def _is_uniticker_dump(raw: str) -> bool:
    matched = 0
    for line in raw.splitlines():
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) < 10:
            continue
        market_at = next((index for index, cell in enumerate(cells) if cell in _UNITICKER_MARKETS), None)
        if market_at is None:
            continue
        if market_at == 0:
            return False
        if market_at >= 3 and cells[0].replace(".", "", 1).isdigit():
            matched += 1
            if matched >= 2:
                return True
    return False


def _parse_uniticker_grid(raw: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        record = _uniticker_record(line)
        if record:
            records.append(record)
    if len(records) < 2:
        return []
    return _rows_to_payloads(records, None)


def _uniticker_record(line: str) -> dict[str, Any] | None:
    cells = [cell.strip() for cell in line.split("\t")]
    if len(cells) < 8:
        return None
    market_at = next((index for index, cell in enumerate(cells) if cell in _UNITICKER_MARKETS), None)
    if market_at is None:
        return None
    rest = cells[market_at + 1 :]
    if len(rest) < 3:
        return None
    record: dict[str, Any] = {}
    for index, field in enumerate(_UNITICKER_AFTER_MARKET):
        if index >= len(rest):
            break
        value = rest[index]
        if value:
            record[field] = value
    if not record.get("symbol") or not record.get("price"):
        return None
    return record


def _parse_append(path: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    try:
        data = path.read_bytes()
    except OSError:
        return [], offset
    if offset >= len(data):
        return [], len(data)
    chunk = data[offset:]
    text = _decode_bytes(chunk)
    if not text.endswith(("\n", "\r")):
        last_break = max(text.rfind("\n"), text.rfind("\r"))
        if last_break < 0:
            return [], offset
        text = text[: last_break + 1]
        chunk = chunk[: last_break + 1]
    hint = _symbol_from_name(path.name)
    uniticker = _parse_uniticker_grid(text)
    if uniticker:
        return uniticker, offset + len(chunk)
    header = _header_from_file(path)
    payloads = _parse_table(text, hint, header=header, has_header=False)
    return payloads, offset + len(chunk)


def _header_from_file(path: Path) -> list[str]:
    raw = _read_text(path)
    first = raw.splitlines()[0] if raw else ""
    dialect = _detect_dialect(first)
    return next(csv.reader([first], dialect=dialect), [])


def _parse_json(raw: str, hint: str | None) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    if isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
        return _rows_to_payloads(rows, hint)
    if not isinstance(payload, dict):
        return []
    if hint and not payload.get("symbol"):
        payload = {**payload, "symbol": hint}
    if any(key in payload for key in ("ticks", "trades", "events", "bids", "asks", "order_book", "price")):
        return [payload]
    rows = payload.get("data") or payload.get("rows") or []
    if isinstance(rows, list):
        return _rows_to_payloads([item for item in rows if isinstance(item, dict)], hint)
    return []


def _parse_table(raw: str, hint: str | None, *, header: list[str] | None = None, has_header: bool = True) -> list[dict[str, Any]]:
    sample = raw.lstrip("\ufeff")
    dialect = _detect_dialect("\n".join(sample.splitlines()[:4]))
    reader = csv.reader(io.StringIO(sample), dialect=dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return []
    if has_header:
        header = rows[0]
        body = rows[1:]
        if not _map_header(header) and _looks_numeric(header):
            body = [header, *body]
            header = []
    else:
        body = rows
        header = header or []
    columns = _map_header(header) or _positional_columns(body[0] if body else [])
    records: list[dict[str, Any]] = []
    for row in body:
        record: dict[str, Any] = {}
        for index, cell in enumerate(row):
            key = columns.get(index)
            if key:
                record[key] = cell.strip()
        if hint and not record.get("symbol"):
            record["symbol"] = hint
        if record:
            records.append(record)
    return _rows_to_payloads(records, hint)


def _rows_to_payloads(rows: list[dict[str, Any]], hint: str | None) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    book_bids: list[dict[str, Any]] = []
    book_asks: list[dict[str, Any]] = []
    book_symbol = hint
    for row in rows:
        ticker = str(row.get("symbol") or hint or "").strip().upper()
        ticker = ticker.split(".", 1)[0]
        if ticker and not re.fullmatch(r"\d{4}", ticker):
            continue
        bid = _clean_number(row.get("bid"))
        ask = _clean_number(row.get("ask"))
        price = _clean_number(row.get("price"))
        qty = _clean_number(row.get("quantity"))
        if ticker and price is not None:
            snapshot = bid is not None or ask is not None or qty is None
            payload: dict[str, Any] = {
                "type": "quote" if snapshot else "trade",
                "symbol": ticker,
                "price": price,
                "quantity": 0 if snapshot else qty,
                "side": row.get("side"),
                "event_time": row.get("time"),
            }
            if qty is not None:
                payload["session_volume"] = qty
            value = _clean_number(row.get("value"))
            if value is not None:
                payload["value_traded"] = value
            change = _clean_number(row.get("change_percent"))
            if change is not None:
                payload["change_percent"] = change
            for extra_key in ("open", "high", "low", "prev_close", "net_flow", "liquidity_flow", "liquidity_pct", "trades"):
                extra = _clean_number(row.get(extra_key))
                if extra is not None:
                    payload[extra_key] = extra
            payloads.append(payload)
            if bid is not None or ask is not None:
                payloads.append(
                    {
                        "type": "depth_snapshot",
                        "symbol": ticker,
                        "bids": [{"price": bid, "quantity": _clean_number(row.get("bid_size")) or 0}] if bid is not None else [],
                        "asks": [{"price": ask, "quantity": _clean_number(row.get("ask_size")) or 0}] if ask is not None else [],
                        "best_bid": bid,
                        "best_ask": ask,
                    }
                )
            continue
        if bid is not None or ask is not None:
            book_symbol = ticker or book_symbol
            if bid is not None:
                book_bids.append({"price": bid, "quantity": _clean_number(row.get("bid_size") or row.get("quantity")) or 0})
            if ask is not None:
                book_asks.append({"price": ask, "quantity": _clean_number(row.get("ask_size") or row.get("quantity")) or 0})
    if book_symbol and (book_bids or book_asks):
        payloads.append(
            {
                "type": "depth_snapshot",
                "symbol": book_symbol,
                "bids": book_bids,
                "asks": book_asks,
                "best_bid": book_bids[0]["price"] if book_bids else None,
                "best_ask": book_asks[0]["price"] if book_asks else None,
            }
        )
    return payloads


def _clean_number(value: Any) -> str | None:
    if value in (None, ""):
        return None
    token = str(value).strip().replace(",", "").replace("،", "").replace("%", "")
    if token in {"", "-", "—"}:
        return None
    try:
        float(token)
    except ValueError:
        return None
    return token


def _looks_numeric(row: list[str]) -> bool:
    if not row:
        return False
    numeric = 0
    for cell in row:
        token = cell.strip().replace(",", "")
        if not token:
            continue
        try:
            float(token)
        except ValueError:
            return False
        numeric += 1
    return numeric >= 2


def _positional_columns(row: list[str]) -> dict[int, str]:
    width = len(row)
    if width >= 4:
        return {0: "time", 1: "price", 2: "quantity", 3: "side"}
    if width == 3:
        return {0: "time", 1: "price", 2: "quantity"}
    if width == 2:
        return {0: "price", 1: "quantity"}
    return {}


def _map_header(header: list[str]) -> dict[int, str]:
    mapped: dict[int, str] = {}
    for index, raw in enumerate(header):
        token = _norm(raw)
        for field, aliases in _HEADER_ALIASES.items():
            if token in aliases:
                mapped[index] = field
                break
    return mapped


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", value.lower().strip())


def _symbol_from_name(name: str) -> str | None:
    match = _SYMBOL_IN_NAME.search(name)
    return match.group(1) if match else None


def _detect_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
        return dialect


def _read_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return _decode_bytes(data)


def _decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
