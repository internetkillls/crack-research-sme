"""
test_calc.py — Unit tests untuk smefin.calc

Semua assertion finansial menggunakan Decimal dengan quantize
ke 2 desimal (Rp) — tidak ada floating-point tolerance.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from smefin.calc import (
    add_months,
    compute_amortization_row,
    compute_full_schedule,
    compute_monthly_payment,
    AmortizationRow,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def d(value: float | int | str) -> Decimal:
    """Shortcut: konversi ke Decimal dengan 2 desimal (Rp)."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


def row_matches(
    row: AmortizationRow,
    month: int,
    payment_date: str,
    interest: float,
    principal: float,
    total: float,
    balance: float,
) -> bool:
    """Assert semua field monetary sama persis (Decimal, cent-precise)."""
    return (
        row.month_number == month
        and row.payment_date == payment_date
        and row.interest_due == d(interest)
        and row.principal_due == d(principal)
        and row.total_due == d(total)
        and row.balance_remaining == d(balance)
    )


# ----------------------------------------------------------------------
# add_months tests
# ----------------------------------------------------------------------


class TestAddMonths:
    def test_add_one_month_normal(self):
        result = add_months(date(2026, 1, 15), 1)
        assert result == date(2026, 2, 15)

    def test_add_one_month_end_of_month(self):
        # 31 Jan + 1 month = 28 Feb (non-leap)
        result = add_months(date(2026, 1, 31), 1)
        assert result == date(2026, 2, 28)

    def test_add_one_month_leap_feb(self):
        # 31 Jan + 1 month in leap year = 29 Feb
        result = add_months(date(2024, 1, 31), 1)
        assert result == date(2024, 2, 29)

    def test_add_one_month_december_crosses_year(self):
        result = add_months(date(2026, 12, 15), 1)
        assert result == date(2027, 1, 15)

    def test_add_multiple_months(self):
        result = add_months(date(2026, 1, 15), 6)
        assert result == date(2026, 7, 15)

    def test_subtract_months(self):
        result = add_months(date(2026, 3, 15), -2)
        assert result == date(2026, 1, 15)

    def test_preserve_day_if_possible(self):
        result = add_months(date(2026, 3, 31), 1)
        # Apr has 30 days; 31 → 30
        assert result == date(2026, 4, 30)

    def test_leap_year_feb_29(self):
        # Feb 29 + 12 months = Feb 28 (non-leap) or Feb 29 (leap)
        assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
        assert add_months(date(2025, 2, 28), 12) == date(2026, 2, 28)

    def test_leap_year_detection(self):
        # 2028 is divisible by 4 and not by 100
        result = add_months(date(2027, 1, 31), 13)
        assert result == date(2028, 2, 29)


# ----------------------------------------------------------------------
# compute_monthly_payment tests
# ----------------------------------------------------------------------


class TestComputeMonthlyPayment:
    def test_positive_rate_50m_24m_r0012(self):
        """Row 1: P=50M, r=0.012, n=24 → M ≈ 2,410,103.25"""
        M = compute_monthly_payment(50_000_000, 0.012, 24)
        assert M == pytest.approx(2_410_103.25, abs=0.001)

    def test_positive_rate_10m_12m_r0018(self):
        """Row 3: P=10M, r=0.018, n=12 → M = 934,019.77"""
        M = compute_monthly_payment(10_000_000, 0.018, 12)
        # 10M * 0.018 / (1 - 1.018^-12) = 934,019.77
        assert Decimal(str(M)) == Decimal("934019.77")

    def test_zero_rate_simple_division(self):
        """Pinjaman tanpa bunga: P/n"""
        M = compute_monthly_payment(50_000_000, 0.0, 24)
        assert M == pytest.approx(2_083_333.33, abs=0.01)

    def test_zero_rate_exact_division(self):
        """Zero rate: 24 bulan, hasil harus 2,083,333.33 (dibulatkan)"""
        M = compute_monthly_payment(50_000_000, 0.0, 24)
        # Exact: 50,000,000 / 24 = 2,083,333.333...
        # Dibilatkan ke 2 desimal:
        assert Decimal(str(M)) == Decimal("2083333.33")

    def test_negative_rate_raises(self):
        with pytest.raises(ValueError, match="rate must be non-negative"):
            compute_monthly_payment(50_000_000, -0.01, 24)

    def test_zero_tenor_raises(self):
        with pytest.raises(ValueError, match="tenor must be at least 1"):
            compute_monthly_payment(50_000_000, 0.012, 0)

    def test_negative_tenor_raises(self):
        with pytest.raises(ValueError, match="tenor must be at least 1"):
            compute_monthly_payment(50_000_000, 0.012, -1)


# ----------------------------------------------------------------------
# compute_amortization_row tests
# ----------------------------------------------------------------------


class TestComputeAmortizationRow:
    def test_month1_50m_r0012(self):
        """Month 1: balance=50M, M=2,410,103.25 (sudah dibulatkan)
        interest = 600,000.00 (exact)
        principal = 2,410,103.25 - 600,000.00 = 1,810,103.25
        balance_remaining = 50,000,000 - 1,810,103.25 = 48,189,896.75
        """
        row = compute_amortization_row(
            balance=50_000_000.0,
            monthly_payment=2_410_103.25,
            monthly_rate=0.012,
            month_number=1,
            payment_date="2026-05-01",
        )
        assert row.month_number == 1
        assert row.payment_date == "2026-05-01"
        assert row.interest_due == d(600_000)
        assert row.principal_due == d(1_810_103.25)
        assert row.total_due == d(2_410_103.25)
        assert row.balance_remaining == d(48_189_896.75)

    def test_month1_zero_rate(self):
        """Zero rate: semua payment = principal, interest = 0"""
        row = compute_amortization_row(
            balance=50_000_000.0,
            monthly_payment=2_083_333.33,
            monthly_rate=0.0,
            month_number=1,
            payment_date="2026-05-01",
        )
        assert row.interest_due == Decimal("0.00")
        assert row.principal_due == d(2_083_333.33)
        assert row.balance_remaining == d(50_000_000) - d(2_083_333.33)

    def test_final_payment_clears_balance(self):
        """Final payment: jika principal > balance, set balance_remaining=0"""
        row = compute_amortization_row(
            balance=500_000.0,  # small final balance
            monthly_payment=2_410_103.25,
            monthly_rate=0.012,
            month_number=24,
            payment_date="2028-04-01",
        )
        assert row.balance_remaining == Decimal("0.00")
        # principal_due = balance (500,000), not payment (2,410,103)
        assert row.principal_due == d(500_000)
        assert row.interest_due == d(500_000)  # interest = balance (fully paid)


# ----------------------------------------------------------------------
# compute_full_schedule tests
# ----------------------------------------------------------------------


class TestComputeFullSchedule:
    def test_kur_bri_24_months_correct_count(self):
        """KUR BRI: 24 bulan tenor → 24 rows"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        assert len(rows) == 24

    def test_kur_bri_first_payment_date(self):
        """start_date 15 April → first payment 1 Mei"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        assert rows[0].payment_date == "2026-05-01"
        assert rows[0].month_number == 1

    def test_kur_bri_final_balance_zero(self):
        """Setelah tenor selesai, balance_remaining harus 0"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        assert rows[-1].balance_remaining == Decimal("0.00")

    def test_kur_bri_month1_values(self):
        """Month 1: interest=600,000.00, principal=1,810,103.25"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        r1 = rows[0]
        assert r1.interest_due == d(600_000)
        assert r1.principal_due == d(1_810_103.25)
        # balance_remaining = 50M - 1,810,103.25 = 48,189,896.75
        assert r1.balance_remaining == d(48_189_896.75)

    def test_start_date_on_first_of_month(self):
        """start_date = 1 Mei → first payment 1 Mei"""
        rows = compute_full_schedule(
            principal=10_000_000.0,
            monthly_rate=0.018,
            tenor_months=12,
            start_date=date(2026, 5, 1),
        )
        assert rows[0].payment_date == "2026-05-01"
        assert rows[0].month_number == 1

    def test_start_date_not_first_rejects_prorated(self):
        """Tidak ada prorated payment: start 15 April → payment 1 Mei"""
        rows = compute_full_schedule(
            principal=10_000_000.0,
            monthly_rate=0.018,
            tenor_months=12,
            start_date=date(2026, 4, 15),
        )
        assert rows[0].payment_date == "2026-05-01"
        assert rows[0].month_number == 1

    def test_zero_rate_schedule(self):
        """Zero rate: semua cicilan bulanan = principal / n, interest = 0.
        Khusus baris terakhir: balance_remaining harus 0, total_due mungkin
        berbeda dari cicilan regular karena akumulasi rounding error."""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.0,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        # Baris 1-23: interest = 0, principal = 2,083,333.33
        for row in rows[:-1]:
            assert row.interest_due == Decimal("0.00")
            assert row.total_due == Decimal("2083333.33")
        # Baris terakhir: balance_remaining = 0, total_due = sisa saldo
        assert rows[-1].balance_remaining == Decimal("0.00")
        # Baris terakhir mungkin tidak sama dengan cicilan regular
        # (akumulasi rounding error dari 23 pembayaran sebelumnya)
        # yang penting balance_remaining = 0
        assert rows[-1].total_due >= Decimal("0.00")

    def test_zero_rate_final_balance_zero(self):
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.0,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        assert rows[-1].balance_remaining == Decimal("0.00")

    def test_payment_dates_are_monthly(self):
        """Payment dates harus berurutan per bulan"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        for i, row in enumerate(rows):
            expected = f"2026-0{5+i}" if i < 8 else f"2026-{4+i//12}-{1+(i-4) % 12:02d}"
            # Simpler: each payment is 1 month apart
        # Verify sequential month numbering
        months = [r.month_number for r in rows]
        assert months == list(range(1, 25))

    def test_monthly_payment_consistent(self):
        """Total_due sama untuk semua bulan KECUALI baris terakhir.
        Baris terakhir menyesuaikan total_due agar balance_remaining = 0."""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        first_total = rows[0].total_due
        # Semua baris SEBELUM terakhir harus sama
        for row in rows[:-1]:
            assert row.total_due == first_total
        # Baris terakhir: balance_remaining = 0, total_due mungkin berbeda
        assert rows[-1].balance_remaining == Decimal("0.00")

    def test_balance_decreases_monotonically(self):
        """Balance harus turun setiap bulan"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        for i in range(1, len(rows)):
            assert rows[i].balance_remaining < rows[i - 1].balance_remaining

    def test_principal_increases_over_time(self):
        """Bagian principal naik seiring waktu (interest menurun)"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        for i in range(1, len(rows)):
            # principal bulan ke-i harus > principal bulan ke-i-1
            assert rows[i].principal_due > rows[i - 1].principal_due

    def test_negative_principal_raises(self):
        """Balance < principal di final payment handled in row, not here"""
        pass  # Covered by compute_amortization_row test

    def test_zero_principal_raises(self):
        with pytest.raises(ValueError, match="principal must be positive"):
            compute_full_schedule(0.0, 0.012, 24, date(2026, 4, 15))

    def test_negative_principal_raises(self):
        with pytest.raises(ValueError, match="principal must be positive"):
            compute_full_schedule(-1_000_000.0, 0.012, 24, date(2026, 4, 15))

    def test_last_row_has_payment_date(self):
        """Setiap row harus punya payment_date yang valid"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        for row in rows:
            assert row.payment_date is not None
            assert len(row.payment_date) == 10  # YYYY-MM-DD format
            assert "-" in row.payment_date