from app.services.shariah import company_name_for, resolve_listed_company, search_listed_companies


def test_anaam_is_bound_to_4061() -> None:
    assert company_name_for("4061") == "أنعام القابضة"
    assert resolve_listed_company("4061") == ("4061", "أنعام القابضة")
    assert resolve_listed_company("أنعام") == ("4061", "أنعام القابضة")


def test_americana_and_alamar_are_not_swapped() -> None:
    assert company_name_for("6015") == "أمريكانا"
    assert company_name_for("6014") == "الآمار"


def test_follow_query_by_official_short_name() -> None:
    resolved = resolve_listed_company("الراجحي")
    assert resolved is not None
    assert resolved[0] == "1120"


def test_search_listed_companies_returns_symbol_with_name() -> None:
    matches = search_listed_companies("أنعام")
    assert matches
    assert matches[0] == ("4061", "أنعام القابضة")
