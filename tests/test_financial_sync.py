from collections.abc import Iterator
from email import message_from_string
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.routers.compliance import router as compliance_router
from app.services.email_alert_service import EmailAlertService
from app.services.financial_sync import FinancialSyncService
from app.services.shariah import is_prohibited, reset_status_overlay


@pytest.fixture(autouse=True)
def _reset_overlay() -> Iterator[None]:
    reset_status_overlay()
    yield
    reset_status_overlay()


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_email": "",
        "sender_password": "",
        "alert_recipient_email": "",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)


def _service(email: MagicMock | None = None) -> FinancialSyncService:
    return FinancialSyncService(_settings(), email_service=email or MagicMock())


def test_same_category_does_not_send_email() -> None:
    email = MagicMock()
    service = _service(email)
    changed = service.check_and_alert_changes("1120", "مصرف الراجحي", "PURE", "نقي")
    assert changed is False
    email.send_alert.assert_not_called()


def test_changed_category_sends_alert_and_updates_store() -> None:
    email = MagicMock()
    email.send_alert.return_value = True
    service = _service(email)
    changed = service.apply_scheduled("1120", "مصرف الراجحي", "MIXED")
    assert changed is True
    email.send_alert.assert_called_once_with("مصرف الراجحي", "1120", "PURE", "MIXED")
    assert service.stored_category("1120") == "MIXED"


def test_sync_scheduled_alerts_only_drifted_rows() -> None:
    email = MagicMock()
    email.send_alert.return_value = True
    service = _service(email)
    changes = service.sync_scheduled(
        [
            {"symbol": "1120", "companyNameAr": "مصرف الراجحي", "currentStatus": "PURE"},
            {"symbol": "1010", "name": "بنك الرياض", "status": "MIXED"},
        ]
    )
    assert [row["symbol"] for row in changes] == ["1010"]
    assert changes[0]["old_category"] == "PROHIBITED"
    assert changes[0]["new_category"] == "MIXED"
    email.send_alert.assert_called_once()
    assert is_prohibited("1010") is False


def test_sync_from_source_is_quiet_when_file_matches_store() -> None:
    email = MagicMock()
    service = _service(email)
    assert service.sync_from_source() == []
    email.send_alert.assert_not_called()


def test_email_alert_skips_when_smtp_is_not_configured() -> None:
    service = EmailAlertService(_settings())
    assert service.enabled is False
    assert service.send_alert("مصرف الراجحي", "1120", "PURE", "MIXED") is False


def test_email_alert_sends_html_via_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = False
    factory = MagicMock(return_value=smtp)
    monkeypatch.setattr("app.services.email_alert_service.smtplib.SMTP", factory)

    service = EmailAlertService(
        _settings(
            sender_email="alerts@rizg.local",
            sender_password="app-password",
            alert_recipient_email="alhwez@gmail.com",
        )
    )
    assert service.send_alert("الراجحي", "1120", "شركات ضعيفة النمو ⚠️لتجنبها", "قلاع النمو والعوائد المتينة 🏰") is True
    factory.assert_called_once_with("smtp.gmail.com", 587, timeout=20)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("alerts@rizg.local", "app-password")
    smtp.sendmail.assert_called_once()
    _sender, recipient, raw = smtp.sendmail.call_args.args
    assert recipient == "alhwez@gmail.com"
    parsed = message_from_string(raw)
    html = parsed.get_payload()[1].get_payload(decode=True).decode("utf-8")
    assert "1120" in html
    assert "أبو نايف" in html
    assert "قلاع النمو" in html
    assert "text/html" in raw


def test_email_alert_skips_identical_categories() -> None:
    service = EmailAlertService(
        _settings(sender_email="alerts@rizg.local", sender_password="secret")
    )
    assert service.send_alert("الراجحي", "1120", "قلاع النمو والعوائد المتينة 🏰", "قلاع النمو والعوائد المتينة 🏰") is False


def test_compliance_sync_route_posts_symbol_only_payload() -> None:
    email = MagicMock()
    email.send_alert.return_value = True
    service = _service(email)
    app = FastAPI()
    app.state.financial_sync = service
    app.include_router(compliance_router)

    response = TestClient(app).post(
        "/api/v1/compliance/sync",
        json={"items": [{"symbol": "1120", "name": "مصرف الراجحي", "currentStatus": "MIXED"}]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] == 1
    assert payload["changes"][0]["old_category"] == "PURE"
    assert payload["changes"][0]["new_category"] == "MIXED"
    email.send_alert.assert_called_once()
