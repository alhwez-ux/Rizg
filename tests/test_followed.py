from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import watchlist as watchlist_router
from app.services.followed import FollowedCompanies


def test_followed_list_roundtrips_across_a_new_store(tmp_path) -> None:
    path = tmp_path / "followed.json"
    book = FollowedCompanies(path)
    assert book.snapshot() == {"saved": False, "companies": []}

    saved = book.replace(
        [
            {"symbol": "1120", "name": "الراجحي"},
            {"symbol": "1120", "name": "مكرر"},
            {"symbol": "22", "name": "ناقص"},
            {"symbol": "2222", "name": "أرامكو"},
        ]
    )
    assert saved["saved"] is True
    assert [item["symbol"] for item in saved["companies"]] == ["1120", "2222"]

    again = FollowedCompanies(path)
    assert again.snapshot()["companies"][0]["name"] == "الراجحي"
    assert again.snapshot()["saved"] is True


def test_clearing_the_follow_list_stays_empty(tmp_path) -> None:
    path = tmp_path / "followed.json"
    book = FollowedCompanies(path)
    book.replace([{"symbol": "2010", "name": "سابك"}])
    cleared = book.replace([])
    assert cleared == {"saved": True, "companies": []}
    assert FollowedCompanies(path).snapshot()["companies"] == []


def test_followed_route_is_shared_by_a_new_client(tmp_path) -> None:
    app = FastAPI()
    app.include_router(watchlist_router.router)
    app.state.followed = FollowedCompanies(tmp_path / "followed.json")
    client = TestClient(app)

    missing = client.get("/api/v1/watchlist/followed")
    assert missing.status_code == 200
    assert missing.json() == {"saved": False, "companies": []}

    saved = client.put(
        "/api/v1/watchlist/followed",
        json={"companies": [{"symbol": "1120", "name": "الراجحي"}, {"symbol": "7010", "name": "اس تي سي"}]},
    )
    assert saved.status_code == 200
    assert [item["symbol"] for item in saved.json()["companies"]] == ["1120", "7010"]

    again = client.get("/api/v1/watchlist/followed")
    assert again.json()["saved"] is True
    assert again.json()["companies"][1]["name"] == "اس تي سي"
