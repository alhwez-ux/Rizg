from datetime import datetime, timedelta, timezone

from app.services.market_news import parse_news_feed

_NAMES = {"2222": "أرامكو السعودية", "1120": "الراجحي"}


def _item(title: str, source: str, url: str, when: str) -> str:
    return (
        "<item>"
        f"<title>{title}</title>"
        "<link>https://news.google.com/articles/sample</link>"
        f"<pubDate>{when}</pubDate>"
        f'<source url="{url}">{source}</source>'
        "</item>"
    )


def test_only_recent_allowlisted_headlines_that_name_a_company_are_kept() -> None:
    now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    fresh = "Tue, 20 Oct 2026 09:00:00 GMT"
    stale = "Sun, 18 Oct 2026 09:00:00 GMT"
    payload = (
        "<rss><channel>"
        + _item("أرامكو السعودية تحقق أرباحاً فصلية - أرقام", "أرقام", "https://www.argaam.com/article", fresh)
        + _item("تراجع سهم الراجحي في تعاملات اليوم - مباشر", "مباشر", "https://www.mubasher.info/news", fresh)
        + _item("ارتفاع أرامكو السعودية مع تراجع في آن واحد - أرقام", "أرقام", "https://www.argaam.com/mixed", fresh)
        + _item("أرامكو السعودية تحقق أرباحاً - مدونة", "مدونة", "https://example.com/post", fresh)
        + _item("أرامكو السعودية تحقق أرباحاً - أرقام", "أرقام", "https://www.argaam.com/old", stale)
        + "</channel></rss>"
    )
    parsed = parse_news_feed(payload, now=now, names=_NAMES)
    assert [row["title"] for row in parsed["positive"]] == ["أرامكو السعودية تحقق أرباحاً فصلية"]
    assert parsed["positive"][0]["companies"] == [{"symbol": "2222", "name": "أرامكو السعودية"}]
    assert parsed["positive"][0]["source"] == "أرقام"
    assert [row["title"] for row in parsed["negative"]] == ["تراجع سهم الراجحي في تعاملات اليوم"]
    assert now - timedelta(hours=24) < datetime.fromisoformat(parsed["negative"][0]["published_at"])
