"""Influential headlines from named newsrooms, limited to the last 24 hours.

A headline is kept only when its publisher is on the allowlist, its time is
inside the window, it names a listed company, and its wording is clearly
positive or clearly negative. Anything else stays out.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.shariah import listed_name_map

logger = logging.getLogger(__name__)

_FEED = "https://news.google.com/rss/search?q=%D8%AA%D8%AF%D8%A7%D9%88%D9%84+when:1d&hl=ar&gl=SA&ceid=SA:ar"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_WINDOW = timedelta(hours=24)
_CACHE_SECONDS = 600.0
_LIMIT = 8

_PUBLISHERS = {
    "argaam.com": "أرقام",
    "mubasher.info": "مباشر",
    "alarabiya.net": "العربية",
    "asharqbusiness.com": "الشرق للأعمال",
    "asharq.com": "الشرق",
    "aawsat.com": "الشرق الأوسط",
    "spa.gov.sa": "واس",
    "reuters.com": "رويترز",
    "aleqt.com": "الاقتصادية",
    "saudiexchange.sa": "تداول",
}

_POSITIVE = (
    "ارتفاع",
    "يرتفع",
    "نمو",
    "أرباح",
    "تربح",
    "عقد",
    "استحواذ",
    "توزيعات",
    "قفزة",
    "مكاسب",
    "توصية بالشراء",
)
_NEGATIVE = (
    "تراجع",
    "يتراجع",
    "انخفاض",
    "ينخفض",
    "خسارة",
    "خسائر",
    "هبوط",
    "غرامة",
    "إنذار",
    "تعليق التداول",
    "توصية بالبيع",
    "خفض التصنيف",
)

_cache: tuple[float, dict[str, Any]] | None = None


def influential_news(*, now: datetime | None = None, fetcher: Any = None) -> dict[str, Any]:
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    global _cache
    stamp = time.monotonic()
    if fetcher is None and _cache and stamp - _cache[0] < _CACHE_SECONDS:
        return dict(_cache[1])
    try:
        payload = fetcher() if fetcher is not None else _download()
    except Exception:
        logger.warning("influential news feed unavailable", exc_info=True)
        payload = ""
    parsed = parse_news_feed(payload, now=clock, names=listed_name_map())
    body = {
        "success": True,
        "as_of": clock.astimezone(timezone.utc).isoformat(),
        "window_hours": 24,
        "positive": parsed["positive"],
        "negative": parsed["negative"],
    }
    if fetcher is None and (parsed["positive"] or parsed["negative"]):
        _cache = (stamp, body)
    return body


def parse_news_feed(payload: str, *, now: datetime, names: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    if not payload or not str(payload).lstrip().startswith("<"):
        return {"positive": positive, "negative": negative}
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return {"positive": positive, "negative": negative}
    earliest = now.astimezone(timezone.utc) - _WINDOW
    aliases = _aliases(names)
    for item in root.findall("./channel/item"):
        row = _item(item, earliest=earliest, aliases=aliases)
        if row is None:
            continue
        bucket = positive if row["tone"] == "positive" else negative
        if len(bucket) >= _LIMIT:
            continue
        bucket.append(row)
    return {"positive": positive, "negative": negative}


def _aliases(names: dict[str, str]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for symbol, name in names.items():
        ticker = str(symbol or "").strip().upper()
        label = str(name or "").strip()
        if len(ticker) != 4 or len(label) < 4 or label == ticker:
            continue
        rows.append((ticker, label, label))
    rows.sort(key=lambda row: len(row[1]), reverse=True)
    return rows


def _item(item: ElementTree.Element, *, earliest: datetime, aliases: list[tuple[str, str, str]]) -> dict[str, Any] | None:
    title = str(item.findtext("title") or "").strip()
    link = str(item.findtext("link") or "").strip()
    published = _published(item.findtext("pubDate"))
    source = item.find("source")
    source_url = str(source.get("url") or "").strip() if source is not None else ""
    if not title or not link or published is None or published < earliest:
        return None
    publisher = _publisher(source_url)
    if publisher is None:
        return None
    headline = title
    suffix = f" - {publisher}"
    if headline.endswith(suffix):
        headline = headline[: -len(suffix)].strip()
    tone = _tone(headline)
    if tone is None:
        return None
    companies = _companies(headline, aliases)
    if not companies:
        return None
    return {
        "title": headline,
        "url": link,
        "source": publisher,
        "source_url": source_url,
        "published_at": published.isoformat(),
        "tone": tone,
        "companies": companies,
    }


def _published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _publisher(url: str) -> str | None:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host:
        return None
    for domain, name in _PUBLISHERS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def _tone(headline: str) -> str | None:
    positive = any(word in headline for word in _POSITIVE)
    negative = any(word in headline for word in _NEGATIVE)
    if positive and not negative:
        return "positive"
    if negative and not positive:
        return "negative"
    return None


def _companies(headline: str, aliases: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for symbol, label, _name in aliases:
        if label not in headline or symbol in seen:
            continue
        seen.add(symbol)
        found.append({"symbol": symbol, "name": label})
        if len(found) >= 3:
            break
    return found


def _download() -> str:
    with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0), headers={"User-Agent": _UA}, follow_redirects=True) as http:
        response = http.get(_FEED)
        response.raise_for_status()
        return response.text
