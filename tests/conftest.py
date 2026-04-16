"""Fixtures untuk semua test modules."""
from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture
def sample_loan_kur():
    """KUR BRI loan standar untuk test repeatability."""
    return dict(
        id="test-kur-001",
        lender_name="KUR BRI",
        principal=50_000_000.0,
        monthly_rate=0.012,
        tenor_months=24,
        start_date=date(2026, 4, 15),
        disbursed_amount=50_000_000.0,
        status="active",
    )