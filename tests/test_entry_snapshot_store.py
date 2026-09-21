from pathlib import Path

from app.services.entry_snapshot_store import EntrySnapshotStore, apply_locked_entries


def test_entry_lock_survives_live_last_move(tmp_path: Path) -> None:
    store = EntrySnapshotStore(tmp_path / "entries.json")
    first = {
        "symbol": "1120",
        "name": "الراجحي",
        "close_price": 96.4,
        "entry_price": "96.10",
        "target_price": "98.10",
        "stop_loss": "95.20",
        "signal_kind": "momentum",
        "confidence_score": 80,
        "confidence": "80%",
        "signal_type": "دخول",
        "reason": "إشارة دخول",
        "entry": True,
    }
    locked = apply_locked_entries(
        [first],
        store=store,
        scan_mode="live",
        session_date="2026-09-21",
        last_prices={"1120": 96.4},
    )
    assert locked[0]["entry_price"] == "96.10"
    assert float(locked[0]["target_price"]) > float(locked[0]["entry_price"]) > float(locked[0]["stop_loss"])

    moved = dict(first)
    moved["close_price"] = 97.8
    moved["entry_price"] = "97.80"
    moved["target_price"] = "99.50"
    moved["stop_loss"] = "96.90"
    again = apply_locked_entries(
        [moved],
        store=store,
        scan_mode="live",
        session_date="2026-09-21",
        last_prices={"1120": 97.8},
    )
    assert again[0]["entry_price"] == "96.10"
    assert again[0]["target_price"] == locked[0]["target_price"]
    assert again[0]["stop_loss"] == locked[0]["stop_loss"]
    assert again[0]["last_price"] == 97.8
    assert again[0]["close_price"] == 97.8
    assert again[0]["target_hit"] is False

    hit = apply_locked_entries(
        [moved],
        store=store,
        scan_mode="live",
        session_date="2026-09-21",
        last_prices={"1120": 98.20},
    )
    assert hit == []

    still_qualified = apply_locked_entries(
        [moved],
        store=store,
        scan_mode="live",
        session_date="2026-09-21",
        last_prices={"1120": 98.40},
    )
    assert still_qualified == []


def test_entry_lock_survives_symbol_dropping_off_the_scan(tmp_path: Path) -> None:
    store = EntrySnapshotStore(tmp_path / "entries.json")
    row = {
        "symbol": "1120",
        "close_price": 96.4,
        "entry_price": "96.10",
        "target_price": "98.10",
        "stop_loss": "95.20",
        "signal_kind": "momentum",
        "confidence_score": 80,
        "confidence": "80%",
        "signal_type": "دخول",
        "reason": "إشارة دخول",
        "entry": True,
    }
    apply_locked_entries([row], store=store, scan_mode="live", session_date="2026-09-21", last_prices={"1120": 96.4})
    apply_locked_entries([], store=store, scan_mode="live", session_date="2026-09-21", last_prices={})
    moved = dict(row)
    moved["entry_price"] = "97.80"
    restored = apply_locked_entries(
        [moved],
        store=store,
        scan_mode="live",
        session_date="2026-09-21",
        last_prices={"1120": 97.8},
    )
    assert restored[0]["entry_price"] == "96.10"


def test_target_hit_returns_only_after_conditions_fire_again(tmp_path: Path) -> None:
    store = EntrySnapshotStore(tmp_path / "entries.json")
    row = {
        "symbol": "1120",
        "close_price": 96.4,
        "entry_price": "96.10",
        "target_price": "98.10",
        "stop_loss": "95.20",
        "signal_kind": "momentum",
        "confidence_score": 80,
        "confidence": "80%",
        "signal_type": "دخول",
        "reason": "إشارة دخول",
        "entry": True,
    }
    apply_locked_entries([row], store=store, scan_mode="live", session_date="2026-09-21", last_prices={"1120": 96.4})
    assert apply_locked_entries(
        [row],
        store=store,
        scan_mode="live",
        session_date="2026-09-21",
        last_prices={"1120": 98.20},
    ) == []

    apply_locked_entries([], store=store, scan_mode="live", session_date="2026-09-21", last_prices={})
    setup = dict(row)
    setup["entry_price"] = "97.80"
    setup["target_price"] = "99.50"
    setup["stop_loss"] = "96.90"
    fresh = apply_locked_entries(
        [setup],
        store=store,
        scan_mode="live",
        session_date="2026-09-21",
        last_prices={"1120": 97.8},
    )
    assert len(fresh) == 1
    assert fresh[0]["entry_price"] == "97.80"
    assert fresh[0]["target_price"] == "99.50"
    assert fresh[0]["last_price"] == 97.8


def test_apply_quote_updates_last_without_rewriting_entry() -> None:
    from app.services.recommendations_engine import _apply_quote

    row = {
        "symbol": "2222",
        "close_price": 25.7,
        "entry_price": "25.50",
        "target_price": "26.20",
        "stop_loss": "25.10",
    }
    updated = _apply_quote(row, {"price": 26.05})
    assert updated is not None
    assert updated["entry_price"] == "25.50"
    assert updated["target_price"] == "26.20"
    assert updated["stop_loss"] == "25.10"
    assert updated["last_price"] == 26.05
    assert updated["close_price"] == 26.05
