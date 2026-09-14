"""Copy TickChart Live market watch and push it straight into local Rizg."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.tickchart_autosync import _is_uniticker_dump, parse_export_text
from app.services.tasi_clock import session_phase

EXPORT_PATH = Path.home() / "AppData" / "Local" / "UniTicker" / "TCLive" / "Export" / "tasi_watch.txt"
DEFAULT_API = "http://127.0.0.1:8000"


def looks_like_watch(text: str) -> bool:
    if "السعودية" not in text:
        return False
    if _is_uniticker_dump(text):
        return True
    return len(parse_export_text(text, "tasi_watch.txt")) >= 2


def push_to_rizg(text: str, api: str) -> int:
    payload = json.dumps({"filename": "tasi_watch.txt", "content": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{api.rstrip('/')}/api/v1/tickchart/upload",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        body = json.loads(response.read().decode("utf-8"))
    return int(body.get("ingested") or 0)


def save_export(text: str) -> Path:
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(text, encoding="utf-8")
    return EXPORT_PATH


def copy_from_tickerchart() -> str:
    if sys.platform != "win32":
        raise RuntimeError("هذا السكربت يعمل على ويندوز فقط")
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length < 3:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        if "TickerChart" in title or "تكرتشارت" in title:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(_enum, 0)
    if not found:
        raise RuntimeError("تكرتشارت غير مفتوح — شغّل TickerChart Live واترك متابع السوق ظاهراً")

    hwnd = found[0]
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)

    def _tap(*codes: int) -> None:
        for code in codes:
            user32.keybd_event(code, 0, 0, 0)
        for code in reversed(codes):
            user32.keybd_event(code, 0, 2, 0)

    vk_control = 0x11
    _tap(vk_control, 0x41)
    time.sleep(0.15)
    _tap(vk_control, 0x43)
    time.sleep(0.35)
    return _clipboard_text()


def _clipboard_text() -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    cf_unicode = 13
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(cf_unicode)
        if not handle:
            return ""
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""
        try:
            return ctypes.wstring_at(locked)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def sync_once(api: str) -> int:
    text = copy_from_tickerchart().strip()
    if not looks_like_watch(text):
        raise RuntimeError("النسخ لم يُخرج متابع السوق — اضغط داخل جدول الأسهم ثم أعد المحاولة")
    save_export(text)
    quotes = [item for item in parse_export_text(text, "tasi_watch.txt") if item.get("type") == "quote"]
    ingested = push_to_rizg(text, api)
    print(
        f"{datetime.now().strftime('%H:%M:%S')}  أُدخل {ingested} صفّاً  |  أسهم {len(quotes)}  |  {EXPORT_PATH}",
        flush=True,
    )
    return ingested


def main() -> int:
    parser = argparse.ArgumentParser(description="تحديث رزق مباشرة من متابع سوق تكرتشارت")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--interval", type=float, default=20, help="ثوانٍ بين كل تحديث")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    print("تكرتشارت → رزق  |  اترك متابع السوق مفتوحاً  |  Ctrl+C للإيقاف", flush=True)
    while True:
        phase = session_phase()
        try:
            sync_once(args.api)
        except Exception as exc:
            print(f"{datetime.now().strftime('%H:%M:%S')}  تعذر التحديث: {exc}", flush=True)
        if args.once:
            return 0
        wait = max(5.0, args.interval)
        if phase not in {"open", "auction", "preopen"}:
            wait = max(wait, 60.0)
        time.sleep(wait)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nتوقف المزامنة", flush=True)
        raise SystemExit(0)
