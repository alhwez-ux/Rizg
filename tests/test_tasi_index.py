from app.services.tasi_index import quote_from_meta


def test_index_quote_uses_points_and_percent() -> None:
    quote = quote_from_meta(
        {
            "regularMarketPrice": 11234.56,
            "previousClose": 11200.0,
            "regularMarketChange": 34.56,
            "regularMarketChangePercent": 0.3086,
        }
    )
    assert quote is not None
    assert quote["symbol"] == "TASI"
    assert quote["type"] == "index"
    assert quote["value"] == 11234.56
    assert quote["change"] == 34.56
    assert quote["change_percent"] == 0.3086


def test_index_quote_derives_change_from_previous_close() -> None:
    quote = quote_from_meta({"regularMarketPrice": 10500.0, "chartPreviousClose": 10000.0})
    assert quote is not None
    assert quote["change"] == 500.0
    assert quote["change_percent"] == 5.0


def test_index_quote_rejects_an_empty_meta() -> None:
    assert quote_from_meta({}) is None
    assert quote_from_meta(None) is None
