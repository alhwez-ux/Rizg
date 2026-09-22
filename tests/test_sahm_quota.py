from __future__ import annotations

from app.services.sahm_quota import SahmQuota, get_sahm_quota


def test_quota_allows_until_limit() -> None:
    quota = SahmQuota(daily_limit=3, path=None)
    assert quota.allow(3) is True
    assert quota.consume(2) == 1
    assert quota.allow() is True
    quota.consume(1)
    assert quota.allow() is False
    assert quota.exhausted() is True
    assert quota.remaining() == 0


def test_quota_trip_stops_further_calls() -> None:
    quota = SahmQuota(daily_limit=90, path=None)
    quota.consume(4)
    quota.trip("http_429")
    assert quota.exhausted() is True
    assert quota.allow() is False
    assert quota.snapshot()["reason"] == "http_429"
    assert quota.snapshot()["used"] == 90


def test_quota_persists_and_reloads(tmp_path) -> None:
    path = tmp_path / "sahm_quota.json"
    first = SahmQuota(daily_limit=90, path=path)
    first.consume(11)
    second = SahmQuota(daily_limit=90, path=path)
    assert second.snapshot()["used"] == 11
    assert second.remaining() == 79


def test_get_sahm_quota_returns_test_singleton() -> None:
    quota = get_sahm_quota()
    assert quota.remaining() >= 90
    quota.consume(1)
    assert get_sahm_quota() is quota
