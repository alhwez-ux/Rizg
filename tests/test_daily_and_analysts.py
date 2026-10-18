from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.schemas import AnalystConsensusResponse, DailyOpportunitiesResponse
from app.routers.analysts import router as analysts_router
from app.routers.opportunities import router as opportunities_router
from app.services.analyst_consensus import active_consensus
from app.services.daily_opportunities import scan_daily_opportunities
from app.services.entry_snapshot_store import EntrySnapshotStore
from app.services.signals import is_valid_long_plan


def _accum(**overrides):
    row = {
        "symbol": "1120",
        "name": "مصرف الراجحي",
        "last_price": 90.0,
        "atr": 1.1,
        "session_low": 89.4,
        "support": 89.6,
        "block_trades": 5,
        "last_block_value": 2_400_000,
        "institutional_inflow": 8_000_000,
        "institutional_outflow": 400_000,
        "retail_inflow": 900_000,
        "retail_outflow": 1_200_000,
        "institutional_mfi": 95,
        "retail_mfi": 43,
        "clustered": 5,
        "clustered_buys": 5,
        "clustered_sells": 0,
        "cluster_run": 4,
        "near_bid_wall": True,
        "bid_wall": {"price": 89.6, "quantity": 80_000},
        "ask_wall": {"price": 90.2, "quantity": 8_000},
    }
    row.update(overrides)
    return row


def test_daily_board_shows_rebound_setups_not_the_liquid_list(tmp_path: Path) -> None:
    class _Feed:
        def market_rows(self):
            return [
                {"symbol": "1120", "name": "1120", "last_price": 90, "value_traded": 8_000_000, "net_flow": 1_200_000, "session_low": 89.2},
                {"symbol": "2222", "name": "2222", "last_price": 27, "value_traded": 6_000_000, "net_flow": 400_000, "session_low": 26.2, "vwap": 26.6},
                {"symbol": "1180", "name": "1180", "last_price": 40, "value_traded": 9_000_000, "net_flow": 2_000_000},
                {"symbol": "7010", "name": "7010", "last_price": 42, "prior_high": 41.2, "value_traded": 500_000},
            ]

    payload = scan_daily_opportunities(_Feed(), snapshots=[], recommendations=[], store=EntrySnapshotStore(tmp_path / "empty.json"))
    symbols = {row["symbol"] for row in payload["data"]}
    assert symbols == {"1120", "2222", "7010"}
    assert "1180" not in symbols
    named = next(row for row in payload["data"] if row["symbol"] == "1120")
    assert named["name"] == "الراجحي"
    assert named["setup"] == "ارتداد من دعم رئيسي"
    vwap = next(row for row in payload["data"] if row["symbol"] == "2222")
    assert vwap["setup"] == "ارتداد من متوسط السيولة"
    broken = next(row for row in payload["data"] if row["symbol"] == "7010")
    assert broken["setup"] == "اختراق مقاومة يومية"
    assert named["reward_ratio"] >= 1.5


def test_daily_breakout_ignores_todays_close_when_measuring_the_prior_ceiling(tmp_path: Path) -> None:
    class _Quotes:
        def close_history(self, symbol: str):
            assert symbol == "6050"
            return [
                {"date": "2026-10-12", "close": 53.05},
                {"date": "2026-10-13", "close": 58.35},
            ]

    class _Feed:
        _quotes = _Quotes()

        def market_rows(self):
            return [{"symbol": "6050", "last_price": 58.35, "session_date": "2026-10-13"}]

    payload = scan_daily_opportunities(_Feed(), snapshots=[], recommendations=[], store=EntrySnapshotStore(tmp_path / "empty.json"))
    assert payload["count"] == 1
    assert payload["data"][0]["symbol"] == "6050"
    assert payload["data"][0]["setup"] == "اختراق مقاومة يومية"


def test_daily_opportunity_enforces_two_r_and_locks_entry(tmp_path: Path) -> None:
    store = EntrySnapshotStore(tmp_path / "locks.json")
    first = scan_daily_opportunities(snapshots=[_accum()], store=store, recommendations=[])
    assert first["count"] == 1
    row = first["data"][0]
    assert row["reward_ratio"] >= 1.5
    assert is_valid_long_plan(row["entry_price"], row["target_price"], row["stop_loss"])
    assert float(row["target_price"]) > float(row["entry_price"]) > float(row["stop_loss"])

    moved = scan_daily_opportunities(
        snapshots=[_accum(last_price=90.4)],
        store=store,
        recommendations=[
            {
                "symbol": "1120",
                "entry_price": "97.00",
                "target_price": "101.00",
                "stop_loss": "95.00",
                "last_price": 97,
            }
        ],
    )
    again = moved["data"][0]
    assert again["entry_price"] == row["entry_price"]
    assert again["entry_price"] != f"{again['last_price']:.2f}"
    assert float(again["target_price"]) > float(again["entry_price"]) > float(again["stop_loss"])


def test_daily_opportunity_drops_inverted_and_prohibited(tmp_path: Path) -> None:
    store = EntrySnapshotStore(tmp_path / "locks.json")
    payload = scan_daily_opportunities(
        snapshots=[_accum(), _accum(symbol="1010"), _accum(symbol="2222", last_price=26.4)],
        recommendations=[
            {
                "symbol": "1140",
                "name": "البلاد",
                "entry_price": "28.00",
                "target_price": "27.10",
                "stop_loss": "29.40",
                "last_price": 28,
            }
        ],
        store=store,
        pure_only=True,
    )
    symbols = {row["symbol"] for row in payload["data"]}
    assert "1010" not in symbols
    assert "1140" not in symbols
    assert "2222" not in symbols
    assert "1120" in symbols
    assert all(row["shariah_status"] == "PURE" for row in payload["data"])


_LIVE = {"1120": 91.25, "1140": 27.4, "1150": 26.1, "2222": 25.2, "4190": 140.0, "2010": 64.0, "1010": 28.0}


def test_analyst_book_drops_expired_inverted_and_prohibited(tmp_path: Path) -> None:
    store = EntrySnapshotStore(tmp_path / "analyst.json")
    rows = active_consensus(today=date(2026, 9, 24), pure_only=False, last_prices=_LIVE, store=store)
    symbols = {row["symbol"] for row in rows}
    assert "1120" in symbols
    assert "2222" in symbols
    assert "4190" not in symbols
    assert "2010" not in symbols
    assert "1010" not in symbols
    for row in rows:
        assert float(row["target_price"]) > float(row["entry_price"]) > float(row["stop_loss"])
        assert row["houses"]
        assert row["valid_until"] >= "2026-09-24"

    pure = active_consensus(today=date(2026, 9, 24), pure_only=True, last_prices=_LIVE, store=store)
    assert "2222" not in {row["symbol"] for row in pure}
    assert pure
    assert all(row["shariah_status"] == "PURE" for row in pure)


def test_five_day_consensus_ranks_recorded_houses_and_keeps_report_levels() -> None:
    from app.services.analyst_consensus import rolling_consensus

    today = date(2026, 10, 12)
    book = [
        {
            "symbol": "1120",
            "houses": ["الراجحي المالية", "الجزيرة كابيتال"],
            "published_on": "2026-10-10",
            "entry_price": 90,
            "target_price": 99,
            "stop_loss": 86,
            "weight": 1,
        },
        {
            "symbol": "1150",
            "houses": ["دراية المالية"],
            "published_on": "2026-10-11",
            "entry_price": 27,
            "target_price": 31,
            "stop_loss": 25,
            "weight": 3,
        },
        {
            "symbol": "1140",
            "houses": ["البلاد المالية"],
            "published_on": "2026-10-06",
            "entry_price": 28,
            "target_price": 32,
            "stop_loss": 26,
        },
        {
            "symbol": "2222",
            "houses": ["الأهلي كابيتال"],
            "entry_price": 26,
            "target_price": 29,
            "stop_loss": 25,
        },
        {
            "symbol": "2010",
            "houses": ["الراجحي المالية"],
            "published_on": "2026-10-12",
            "entry_price": 64,
            "target_price": 61,
            "stop_loss": 66,
        },
    ]
    rows = rolling_consensus(today=today, window_days=5, last_prices={"1120": 91.5, "1150": 26.4}, book=book)
    assert [row["symbol"] for row in rows] == ["1150", "1120"]
    rich = rows[0]
    assert rich["analyst_count"] == 1
    assert rich["consensus_strength"] == 3
    assert rich["entry_price"] == "27.00"
    assert rich["last_price"] == 26.4
    agreed = rows[1]
    assert agreed["analyst_count"] == 2
    assert agreed["houses"] == ["الراجحي المالية", "الجزيرة كابيتال"]
    assert agreed["entry_low"] == "90.00"
    assert agreed["target_price"] == "99.00"
    assert agreed["stop_loss"] == "86.00"
    assert agreed["last_price"] == 91.5
    assert "1140" not in {row["symbol"] for row in rows}
    assert "2222" not in {row["symbol"] for row in rows}
    assert "2010" not in {row["symbol"] for row in rows}


def test_five_day_exit_list_keeps_only_dated_caution_plans() -> None:
    from app.services.analyst_consensus import rolling_consensus, rolling_exits

    today = date(2026, 10, 19)
    book = [
        {
            "symbol": "4190",
            "houses": ["الراجحي المالية", "الأهلي كابيتال"],
            "stance": "exit",
            "published_on": "2026-10-17",
            "entry_price": 40,
            "target_price": 36,
            "stop_loss": 42,
            "note": "تصريف ملحوظ مع ضعف في النمو",
            "weight": 1,
        },
        {
            "symbol": "1211",
            "houses": ["الرياض المالية"],
            "stance": "caution",
            "published_on": "2026-10-18",
            "note": "ضعف في الأساسيات دون مستويات سعرية",
        },
        {
            "symbol": "2010",
            "houses": ["الراجحي المالية"],
            "published_on": "2026-10-18",
            "entry_price": 64,
            "target_price": 61,
            "stop_loss": 66.5,
        },
        {
            "symbol": "1120",
            "houses": ["الجزيرة كابيتال"],
            "stance": "sell",
            "published_on": "2026-10-10",
            "entry_price": 90,
            "target_price": 80,
            "stop_loss": 94,
        },
        {
            "symbol": "1010",
            "houses": ["دراية المالية"],
            "stance": "avoid",
            "published_on": "2026-10-18",
            "note": "محرم",
        },
    ]
    exits = rolling_exits(today=today, window_days=5, book=book, last_prices={"4190": 39.2})
    assert [row["symbol"] for row in exits] == ["4190", "1211"]
    agreed = exits[0]
    assert agreed["direction"] == "exit"
    assert agreed["analyst_count"] == 2
    assert agreed["entry_price"] == "40.00"
    assert agreed["target_price"] == "36.00"
    assert agreed["stop_loss"] == "42.00"
    assert agreed["note"] == "تصريف ملحوظ مع ضعف في النمو"
    assert agreed["last_price"] == 39.2
    assert agreed["symbol"] == "4190"
    plain = exits[1]
    assert plain["entry_price"] == ""
    assert plain["target_price"] == ""
    assert plain["stop_loss"] == ""
    assert plain["note"] == "ضعف في الأساسيات دون مستويات سعرية"
    assert rolling_consensus(today=today, window_days=5, book=book) == []


def test_analyst_entry_locks_live_print_and_ignores_book_price(tmp_path: Path) -> None:
    store = EntrySnapshotStore(tmp_path / "analyst-lock.json")
    first = active_consensus(today=date(2026, 9, 24), last_prices=_LIVE, store=store)
    row = next(item for item in first if item["symbol"] == "1120")
    assert row["entry_price"] == "91.25"
    assert row["entry_price"] != "86.40"
    assert float(row["target_price"]) > float(row["entry_price"]) > float(row["stop_loss"])
    assert row["last_price"] == 91.25

    moved = active_consensus(
        today=date(2026, 9, 24),
        last_prices={**_LIVE, "1120": 94.0},
        store=store,
    )
    again = next(item for item in moved if item["symbol"] == "1120")
    assert again["entry_price"] == row["entry_price"]
    assert again["target_price"] == row["target_price"]
    assert again["stop_loss"] == row["stop_loss"]
    assert again["last_price"] == 94.0
    assert again["entry_price"] != f"{again['last_price']:.2f}"


def test_daily_and_analyst_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.opportunities.scan_daily_opportunities",
        lambda *args, **kwargs: scan_daily_opportunities(
            snapshots=[_accum()],
            store=EntrySnapshotStore(tmp_path / "endpoint.json"),
            recommendations=[],
            pure_only=kwargs.get("pure_only", False),
        ),
    )

    class _Feed:
        last_prices = _LIVE

        def smart_money_snapshots(self):
            return [_accum()]

    app = FastAPI()
    app.include_router(opportunities_router)
    app.include_router(analysts_router)
    app.state.tickchart = _Feed()
    app.state.analyst_entry_store = EntrySnapshotStore(tmp_path / "analyst-endpoint.json")
    client = TestClient(app)

    daily = client.get("/api/v1/opportunities/daily")
    assert daily.status_code == 200
    body = DailyOpportunitiesResponse.model_validate(daily.json())
    assert body.count == 1
    assert body.data[0].reward_ratio >= 1.5
    assert float(body.data[0].target_price) > float(body.data[0].entry_price) > float(body.data[0].stop_loss)

    analysts = client.get("/api/v1/analysts/consensus")
    assert analysts.status_code == 200
    book = AnalystConsensusResponse.model_validate(analysts.json())
    assert book.count >= 1
    assert all(float(row.target_price) > float(row.entry_price) > float(row.stop_loss) for row in book.data)
    assert "1010" not in {row.symbol for row in book.data}
