from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.services.sahm_quota import SahmQuota, reset_sahm_quota_for_tests, set_sahm_quota_for_tests


@pytest.fixture(autouse=True)
def _isolate_sahm_quota() -> Iterator[None]:
    """Keep the free-tier counter in memory so tests never share production quota."""

    set_sahm_quota_for_tests(SahmQuota(daily_limit=10_000, path=None))
    yield
    reset_sahm_quota_for_tests()
