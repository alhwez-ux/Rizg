from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.services.sahm_quota import SahmQuota, reset_sahm_quota_for_tests, set_sahm_quota_for_tests
from app.services.liquidity_engine import reset_live_signal_engine
from app.services.signals import SignalEngine


@pytest.fixture(autouse=True)
def _isolate_sahm_quota() -> Iterator[None]:
    """Keep the free-tier counter in memory so tests never share production quota."""

    set_sahm_quota_for_tests(SahmQuota(daily_limit=10_000, path=None))
    yield
    reset_sahm_quota_for_tests()


@pytest.fixture(autouse=True)
def _instant_live_signals() -> Iterator[None]:
    """Unit tests of raw tape rules should not wait on the live confirmation latch."""

    reset_live_signal_engine(SignalEngine(confirm_hits=1, sample_seconds=0))
    yield
    reset_live_signal_engine(None)


@pytest.fixture(autouse=True)
def _isolate_sahm_quota() -> Iterator[None]:
    """Keep the free-tier counter in memory so tests never share production quota."""

    set_sahm_quota_for_tests(SahmQuota(daily_limit=10_000, path=None))
    yield
    reset_sahm_quota_for_tests()
