from __future__ import annotations

from typing import Any

import pandas as pd

GROWTH_WEIGHT = 0.30
DIVIDEND_WEIGHT = 0.30
SOLVENCY_WEIGHT = 0.25
PE_WEIGHT = 0.15

CATEGORY_FORTRESS = "قلاع النمو والعوائد المتينة 🏰"
CATEGORY_PROMISING = "شركات تشغيلية واعدة ومستقرة 📈"
CATEGORY_AVERAGE = "شركات ذات أداء متوسط أو متحفظ ⚖️"
CATEGORY_WEAK = "شركات ضعيفة النمو ⚠️لتجنبها"
CATEGORY_LOSER = "الشركات الخاسرة وعالية المخاطر 🔴"

SAMPLE_COMPANIES: list[dict[str, Any]] = [
    {
        "symbol": "1120",
        "name": "الراجحي",
        "profit_growth": 12.5,
        "dividend_yield": 3.2,
        "roe": 18.4,
        "roa": 2.6,
        "pe_ratio": 16.2,
        "net_income": 16000,
    },
    {
        "symbol": "2222",
        "name": "أرامكو السعودية",
        "profit_growth": -2.1,
        "dividend_yield": 6.8,
        "roe": 25.1,
        "roa": 18.4,
        "pe_ratio": 15.5,
        "net_income": 400000,
    },
    {
        "symbol": "2010",
        "name": "سابك",
        "profit_growth": -15.0,
        "dividend_yield": 2.5,
        "roe": 3.2,
        "roa": 1.1,
        "pe_ratio": 35.0,
        "net_income": -500,
    },
    {
        "symbol": "1180",
        "name": "الأهلي",
        "profit_growth": 9.8,
        "dividend_yield": 3.5,
        "roe": 14.2,
        "roa": 1.9,
        "pe_ratio": 12.1,
        "net_income": 14000,
    },
    {
        "symbol": "7010",
        "name": "الاتصالات السعودية",
        "profit_growth": 7.4,
        "dividend_yield": 4.9,
        "roe": 19.8,
        "roa": 8.6,
        "pe_ratio": 17.4,
        "net_income": 12500,
    },
    {
        "symbol": "2280",
        "name": "المراعي",
        "profit_growth": 10.6,
        "dividend_yield": 2.4,
        "roe": 16.1,
        "roa": 8.2,
        "pe_ratio": 22.8,
        "net_income": 2100,
    },
    {
        "symbol": "4030",
        "name": "البحر الأحمر",
        "profit_growth": 1.2,
        "dividend_yield": 0.8,
        "roe": 5.1,
        "roa": 2.0,
        "pe_ratio": 28.4,
        "net_income": 420,
    },
    {
        "symbol": "1211",
        "name": "معادن",
        "profit_growth": -8.0,
        "dividend_yield": 1.1,
        "roe": 4.0,
        "roa": 2.2,
        "pe_ratio": 32.0,
        "net_income": 800,
    },
]

MAJOR_TASI_COMPANIES: list[dict[str, str]] = [
    {"symbol": "2222", "name": "أرامكو السعودية", "sector": "الطاقة"},
    {"symbol": "1120", "name": "الراجحي", "sector": "المصارف"},
    {"symbol": "1180", "name": "الأهلي", "sector": "المصارف"},
    {"symbol": "1010", "name": "الرياض", "sector": "المصارف"},
    {"symbol": "1050", "name": "السعودي الفرنسي", "sector": "المصارف"},
    {"symbol": "1060", "name": "ساب", "sector": "المصارف"},
    {"symbol": "1080", "name": "العربي الوطني", "sector": "المصارف"},
    {"symbol": "1150", "name": "الإنماء", "sector": "المصارف"},
    {"symbol": "1140", "name": "البلاد", "sector": "المصارف"},
    {"symbol": "1020", "name": "الجزيرة", "sector": "المصارف"},
    {"symbol": "1030", "name": "استثمار", "sector": "المصارف"},
    {"symbol": "1111", "name": "مجموعة تداول", "sector": "الخدمات المالية"},
    {"symbol": "2010", "name": "سابك", "sector": "المواد الأساسية"},
    {"symbol": "2020", "name": "سابك للمغذيات الزراعية", "sector": "المواد الأساسية"},
    {"symbol": "1211", "name": "معادن", "sector": "المواد الأساسية"},
    {"symbol": "2290", "name": "ينساب", "sector": "المواد الأساسية"},
    {"symbol": "2310", "name": "سبكيم العالمية", "sector": "المواد الأساسية"},
    {"symbol": "2350", "name": "كيان السعودية", "sector": "المواد الأساسية"},
    {"symbol": "2001", "name": "كيمانول", "sector": "المواد الأساسية"},
    {"symbol": "1320", "name": "أسمنت السعودية", "sector": "المواد الأساسية"},
    {"symbol": "1303", "name": "أسمنت ينبع", "sector": "المواد الأساسية"},
    {"symbol": "1321", "name": "أسمنت الجنوبية", "sector": "المواد الأساسية"},
    {"symbol": "7010", "name": "اس تي سي", "sector": "الاتصالات"},
    {"symbol": "7020", "name": "زين السعودية", "sector": "الاتصالات"},
    {"symbol": "7030", "name": "موبايلي", "sector": "الاتصالات"},
    {"symbol": "2082", "name": "أكوا باور", "sector": "المرافق"},
    {"symbol": "5110", "name": "كهرباء السعودية", "sector": "المرافق"},
    {"symbol": "2280", "name": "المراعي", "sector": "إنتاج الأغذية"},
    {"symbol": "2050", "name": "صافولا", "sector": "إنتاج الأغذية"},
    {"symbol": "2270", "name": "سدافكو", "sector": "إنتاج الأغذية"},
    {"symbol": "4001", "name": "أسواق العثيم", "sector": "تجزئة الأغذية"},
    {"symbol": "4003", "name": "إكسترا", "sector": "التجزئة"},
    {"symbol": "4190", "name": "جرير", "sector": "التجزئة"},
    {"symbol": "4161", "name": "بن داود", "sector": "تجزئة الأغذية"},
    {"symbol": "4013", "name": "د. سليمان الحبيب", "sector": "الرعاية الصحية"},
    {"symbol": "4005", "name": "رعاية", "sector": "الرعاية الصحية"},
    {"symbol": "4004", "name": "دله الصحية", "sector": "الرعاية الصحية"},
    {"symbol": "4009", "name": "المواساة", "sector": "الرعاية الصحية"},
    {"symbol": "8210", "name": "بوبا العربية", "sector": "التأمين"},
    {"symbol": "8010", "name": "التعاونية", "sector": "التأمين"},
    {"symbol": "4030", "name": "البحري", "sector": "النقل"},
    {"symbol": "4261", "name": "أديس", "sector": "الطاقة"},
    {"symbol": "2380", "name": "بترورابغ", "sector": "الطاقة"},
    {"symbol": "2030", "name": "المصافي", "sector": "الطاقة"},
    {"symbol": "1830", "name": "وقت اللياقة", "sector": "الخدمات الاستهلاكية"},
    {"symbol": "1810", "name": "سيرا", "sector": "الخدمات الاستهلاكية"},
    {"symbol": "4260", "name": "بدجت السعودية", "sector": "النقل"},
    {"symbol": "7203", "name": "عِلم", "sector": "البرمجيات والخدمات"},
    {"symbol": "4321", "name": "المراكز العربية", "sector": "إدارة وتطوير العقارات"},
    {"symbol": "4300", "name": "دار الأركان", "sector": "إدارة وتطوير العقارات"},
    {"symbol": "4280", "name": "المملكة", "sector": "الإعلام والترفيه"},
]


class CompanyRankingEngine:
    def __init__(self, companies_financials: list[dict[str, Any]]):
        """
        تستقبل بيانات الشركات وتحتوي على:
        symbol, name, profit_growth, dividend_yield, roe, roa, pe_ratio, net_income
        """
        self.df = pd.DataFrame(list(companies_financials or []))

    def calculate_matrix_score(self) -> pd.DataFrame:
        if self.df.empty:
            return self.df

        frame = self.df.copy()
        for column in ("profit_growth", "dividend_yield", "roe", "roa", "pe_ratio", "net_income"):
            if column not in frame.columns:
                frame[column] = 0.0
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        scored = frame.apply(_score_row, axis=1, result_type="expand")
        scored.columns = ["matrix_score", "category"]
        frame["matrix_score"] = scored["matrix_score"]
        frame["category"] = scored["category"]
        frame = frame.sort_values(
            by=["matrix_score", "symbol"],
            ascending=[False, True],
        ).reset_index(drop=True)
        if "rank" in frame.columns:
            frame = frame.drop(columns=["rank"])
        frame.insert(0, "rank", range(1, len(frame) + 1))
        self.df = frame
        return self.df

    def get_ranked_payload(self) -> list[dict[str, Any]]:
        ranked_df = self.calculate_matrix_score()
        if ranked_df.empty:
            return []
        return [_native_record(row) for row in ranked_df.to_dict(orient="records")]


def _score_row(row: pd.Series) -> pd.Series:
    net_income = _optional_num(row, "net_income")
    if net_income is not None and net_income <= 0:
        return pd.Series([-1000.0, CATEGORY_LOSER])

    growth = _clip_norm(_num(row, "profit_growth"), low=-20.0, high=40.0)
    dividend = _clip_norm(_num(row, "dividend_yield"), low=0.0, high=8.0)
    roe = _clip_norm(_num(row, "roe"), low=0.0, high=30.0)
    roa_raw = row.get("roa")
    roa_value = _num(row, "roe") if pd.isna(roa_raw) else _num(row, "roa")
    roa = _clip_norm(roa_value, low=0.0, high=15.0)
    solvency = 0.6 * roe + 0.4 * roa
    pe = _num(row, "pe_ratio", default=15.0)
    pe_score = _clip_norm(pe, low=8.0, high=35.0, invert=True) if pe > 0 else 0.0

    score = (
        growth * GROWTH_WEIGHT
        + dividend * DIVIDEND_WEIGHT
        + solvency * SOLVENCY_WEIGHT
        + pe_score * PE_WEIGHT
    )
    return pd.Series([round(float(score), 2), _category_for(score)])


def _category_for(score: float) -> str:
    if score > 70:
        return CATEGORY_FORTRESS
    if score > 50:
        return CATEGORY_PROMISING
    if score > 30:
        return CATEGORY_AVERAGE
    return CATEGORY_WEAK


def _clip_norm(value: float, *, low: float, high: float, invert: bool = False) -> float:
    span = high - low
    if span <= 0:
        return 50.0
    ratio = (value - low) / span
    ratio = max(0.0, min(1.0, ratio))
    if invert:
        ratio = 1.0 - ratio
    return ratio * 100.0


def _optional_num(row: pd.Series, key: str) -> float | None:
    try:
        value = row[key]
    except Exception:
        return None
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _num(row: pd.Series, key: str, default: float = 0.0) -> float:
    try:
        value = row[key]
    except Exception:
        return default
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if pd.isna(number):
        return default
    return number


def _native_record(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if value is None or (isinstance(value, float) and pd.isna(value)):
            payload[str(key)] = None
            continue
        if hasattr(value, "item"):
            payload[str(key)] = value.item()
            continue
        payload[str(key)] = value
    payload["matrix_score"] = round(float(payload.get("matrix_score") or 0), 2)
    payload["rank"] = int(payload.get("rank") or 0)
    return payload
