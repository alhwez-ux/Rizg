from typing import Any


class AppError(Exception):
    """Base application error mapped to an HTTP response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "app_error",
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class SymbolNotFoundError(AppError):
    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"No market data found for symbol '{symbol}'",
            status_code=404,
            error_code="symbol_not_found",
            details={"symbol": symbol},
        )


class InvalidQuoteError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            message,
            status_code=422,
            error_code="invalid_quote",
            details=details,
        )


class InvalidTradeError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(
            message,
            status_code=422,
            error_code="invalid_trade",
            details=details,
        )


class InvalidSymbolError(AppError):
    def __init__(self, symbol: str) -> None:
        super().__init__(
            "رمز السهم غير صالح. استخدم رمز تداول من 4 أرقام مثل 4030.",
            status_code=422,
            error_code="invalid_symbol",
            details={"symbol": symbol},
        )


class WatchlistFullError(AppError):
    def __init__(self, max_symbols: int) -> None:
        super().__init__(
            f"قائمة المتابعة ممتلئة (الحد {max_symbols} أسهم).",
            status_code=409,
            error_code="watchlist_full",
            details={"max_symbols": max_symbols},
        )


class ProhibitedSymbolError(AppError):
    def __init__(self, symbol: str) -> None:
        super().__init__(
            "هذا السهم محرّم ولا يُعرض في رادار السيولة",
            status_code=422,
            error_code="prohibited_symbol",
            details={"symbol": symbol},
        )


class TickChartNotConfiguredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "مزود تكرتشارت غير مهيأ. فعّل TICKCHART_ENABLED أو ضع مجلد التصدير في TICKCHART_EXPORT_DIR.",
            status_code=503,
            error_code="tickchart_not_configured",
        )


class TickChartUnauthorizedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "رمز تكرتشارت غير صالح",
            status_code=401,
            error_code="tickchart_unauthorized",
        )


class TickChartNoTickError(AppError):
    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"لا يوجد تدفق لحظي من تكرتشارت للرمز {symbol}",
            status_code=404,
            error_code="tickchart_no_tick",
            details={"symbol": symbol},
        )


class SahmApiError(AppError):
    """Raised when the SAHMK REST API cannot be used or returns an error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        error_code: str = "sahm_api_error",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )
