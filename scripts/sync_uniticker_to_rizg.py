"""Push TickerChart 1-minute quotes into Rizg with no UI and no clicking."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.tasi_clock import session_phase
from app.services.uniticker_flatfiles import collect_live_quotes

LOCAL_API = "http://127.0.0.1:8000"
REMOTE_API = "https://rizg-backend.onrender.com"
LOG_PATH = ROOT / "data" / "tickchart_live" / "uniticker_push.log"


def _configure_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_PATH, encoding="utf-8")]
    if sys.stdout and sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def _fingerprint(quotes: list[dict]) -> tuple:
    return tuple((item.get("symbol"), item.get("price"), item.get("time")) for item in quotes)


def push_quotes(quotes: list[dict], api: str) -> int:
    body = json.dumps(
        {"filename": "uniticker_1m.json", "content": json.dumps(quotes, ensure_ascii=False)},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{api.rstrip('/')}/api/v1/tickchart/upload",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return int(payload.get("ingested") or 0)


def sync_once(apis: list[str], sent: dict[str, tuple]) -> None:
    quotes = collect_live_quotes()
    if not quotes:
        raise RuntimeError("no UniTicker 1-minute quotes yet — keep TickerChart Live open")
    fingerprint = _fingerprint(quotes)
    stamp = datetime.now().strftime("%H:%M:%S")
    for api in apis:
        if sent.get(api) == fingerprint:
            continue
        try:
            ingested = push_quotes(quotes, api)
            sent[api] = fingerprint
            logging.info("%s  %s  symbols=%s ingested=%s", stamp, api, len(quotes), ingested)
        except urllib.error.URLError as exc:
            logging.warning("%s  %s  failed: %s", stamp, api, exc.reason or exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-push UniTicker 1-minute quotes into Rizg")
    parser.add_argument("--api", action="append", dest="apis")
    parser.add_argument("--interval", type=float, default=20)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()
    _configure_logging()
    apis = list(args.apis or [])
    if not apis:
        apis = [LOCAL_API] if args.local_only else [LOCAL_API, REMOTE_API]
    logging.info("UniTicker 1m -> Rizg  interval=%ss  apis=%s", args.interval, ",".join(apis))
    sent: dict[str, tuple] = {}
    while True:
        phase = session_phase()
        try:
            sync_once(apis, sent)
        except Exception as exc:
            logging.warning("sync failed: %s", exc)
        if args.once:
            return 0
        wait = max(15.0, args.interval)
        if phase not in {"open", "auction", "preopen"}:
            wait = max(wait, 90.0)
        time.sleep(wait)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logging.info("stopped")
        raise SystemExit(0)
