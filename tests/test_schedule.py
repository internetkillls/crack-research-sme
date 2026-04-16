"""
test_schedule.py — Unit tests untuk smefin.schedule

Test generate_schedule_for_loan, generate_all_schedules,
compute_monthly_outflow, compute_summary.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from smefin.calc import compute_full_schedule, AmortizationRow
from smefin.schedule import (
    compute_monthly_outflow,
    compute_summary,
    generate_schedule_for_loan,
    MonthlyOutflowRow,
    OutflowSummary,
)


# ----------------------------------------------------------------------
# compute_monthly_outflow tests
# ----------------------------------------------------------------------


class TestComputeMonthlyOutflow:
    def test_empty_schedules(self):
        result = compute_monthly_outflow({}, months=None)
        assert result == []

    def test_single_loan_all_months(self):
        """KUR BRI 24 bulan → 24 distinct months"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        schedules = {"loan-1": rows}
        result = compute_monthly_outflow(schedules)

        assert len(result) == 24
        assert result[0].month == "2026-05-01"
        assert result[0].loan_count == 1
        assert result[0].total_outflow == pytest.approx(2_410_103.25, abs=0.01)
        assert result[0].principal_outflow == pytest.approx(1_810_103.25, abs=0.01)
        assert result[0].interest_outflow == pytest.approx(600_000.0, abs=0.01)

    def test_two_loans_same_month(self):
        """Dua loan dengan first payment sama bulan → loan_count = 2"""
        rows_a = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),  # first payment: 2026-05-01
        )
        rows_b = compute_full_schedule(
            principal=25_000_000.0,
            monthly_rate=0.012,
            tenor_months=12,
            start_date=date(2026, 4, 15),  # first payment: 2026-05-01
        )
        schedules = {"loan-A": rows_a, "loan-B": rows_b}
        result = compute_monthly_outflow(schedules)

        # Month 1: both loans pay
        may = next(r for r in result if r.month == "2026-05-01")
        assert may.loan_count == 2
        # Total: 2,410,103.25 + ~1,351,000 ≈ 3,761,103
        assert may.total_outflow > 3_000_000

    def test_two_loans_different_start_month(self):
        """Loan A mulai April, Loan B mulai Juni → different first payment months"""
        rows_a = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 3, 15),  # first payment: 2026-04-01
        )
        rows_b = compute_full_schedule(
            principal=25_000_000.0,
            monthly_rate=0.012,
            tenor_months=12,
            start_date=date(2026, 5, 15),  # first payment: 2026-06-01
        )
        schedules = {"loan-A": rows_a, "loan-B": rows_b}
        result = compute_monthly_outflow(schedules)

        # April has loan A only
        apr = next((r for r in result if r.month == "2026-04-01"), None)
        if apr:
            assert apr.loan_count == 1

        # June has loan A + B
        jun = next((r for r in result if r.month == "2026-06-01"), None)
        if jun:
            assert jun.loan_count == 2

    def test_months_filter_limits_result(self):
        """months parameter membatasi hasil ke N bulan pertama"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        schedules = {"loan-1": rows}
        result = compute_monthly_outflow(schedules, months=6)

        assert len(result) == 6
        assert result[0].month == "2026-05-01"
        assert result[5].month == "2026-10-01"

    def test_months_filter_after_sort(self):
        """months di-aplikasikan SETELAH sorting, bukan sebelum"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        schedules = {"loan-1": rows}

        # months=None → 24 rows
        all_rows = compute_monthly_outflow(schedules, months=None)
        assert len(all_rows) == 24

        # months=12 → first 12
        twelve = compute_monthly_outflow(schedules, months=12)
        assert len(twelve) == 12
        assert twelve[0].month == all_rows[0].month
        assert twelve[-1].month == all_rows[11].month

    def test_interest_vs_principal_breakdown(self):
        """Month 1: interest = 600,000, principal = ~1.81M"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        schedules = {"loan-1": rows}
        result = compute_monthly_outflow(schedules)

        may = next(r for r in result if r.month == "2026-05-01")
        assert may.principal_outflow + may.interest_outflow == pytest.approx(
            may.total_outflow, abs=0.01
        )

    def test_total_outflow_sum_equals_schedule_total(self):
        """Sum semua total_outflow = sum semua scheduled payments"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        schedules = {"loan-1": rows}
        result = compute_monthly_outflow(schedules)

        total_from_outflow = sum(r.total_outflow for r in result)
        total_from_rows = sum(float(r.total_due) for r in rows)
        assert total_from_outflow == pytest.approx(total_from_rows, abs=1.0)

    def test_results_sorted_chronologically(self):
        """Hasil di-sort ascending by month"""
        rows = compute_full_schedule(
            principal=50_000_000.0,
            monthly_rate=0.012,
            tenor_months=24,
            start_date=date(2026, 4, 15),
        )
        schedules = {"loan-1": rows}
        result = compute_monthly_outflow(schedules)

        months = [r.month for r in result]
        assert months == sorted(months)


# ----------------------------------------------------------------------
# OutflowSummary tests
# ----------------------------------------------------------------------


class TestOutflowSummary:
    def test_empty_outflow_rows(self):
        import tempfile, sqlite3, os
        from smefin.db import init_schema
        import tempfile, sqlite3

        import os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        conn = sqlite3.connect(db_path)
        init_schema(conn)

        rows = []
        summary = compute_summary(rows, conn)

        assert summary.total_deployed == 0.0
        assert summary.total_scheduled == 0.0
        assert summary.avg_monthly_outflow == 0.0
        assert summary.highest_month is None

        conn.close()
        os.unlink(db_path)

    def test_summary_highest_and_lowest(self):
        """Highest = max total_outflow, lowest = min"""
        rows = [
            MonthlyOutflowRow("2026-05-01", 2_000_000.0, 1_000_000.0, 1_000_000.0, 1),
            MonthlyOutflowRow("2026-06-01", 5_000_000.0, 2_500_000.0, 2_500_000.0, 1),
            MonthlyOutflowRow("2026-07-01", 2_000_000.0, 1_000_000.0, 1_000_000.0, 1),
        ]
        import tempfile, sqlite3, os
        from smefin.db import init_schema, insert_loan

        db_path = tempfile.mktemp(suffix=".db")
        conn = sqlite3.connect(db_path)
        init_schema(conn)
        insert_loan({
            "id": "test-loan",
            "lender_name": "Test",
            "principal": 50_000_000.0,
            "monthly_rate": 0.012,
            "tenor_months": 24,
            "start_date": date(2026, 4, 15),
            "disbursed_amount": 50_000_000.0,
            "status": "active",
        }, conn)

        summary = compute_summary(rows, conn)

        assert summary.highest_month == "2026-06-01"
        assert summary.highest_outflow == 5_000_000.0
        assert summary.lowest_month == "2026-05-01"
        assert summary.lowest_outflow == 2_000_000.0
        assert summary.total_deployed == 50_000_000.0

        conn.close()
        os.unlink(db_path)


# ----------------------------------------------------------------------
# generate_schedule_for_loan tests (integration)
# ----------------------------------------------------------------------


class TestGenerateScheduleForLoan:
    def test_generate_stores_correct_row_count(self):
        import tempfile, sqlite3, os
        from smefin.db import init_schema, insert_loan
        from smefin.schedule import generate_schedule_for_loan

        db_path = tempfile.mktemp(suffix=".db")
        conn = sqlite3.connect(db_path)
        init_schema(conn)
        insert_loan({
            "id": "kur-001",
            "lender_name": "KUR BRI",
            "principal": 50_000_000.0,
            "monthly_rate": 0.012,
            "tenor_months": 24,
            "start_date": date(2026, 4, 15),
            "disbursed_amount": 50_000_000.0,
            "status": "active",
        }, conn)

        rows = generate_schedule_for_loan("kur-001", conn)
        assert len(rows) == 24
        assert rows[0].month_number == 1
        assert rows[0].payment_date == "2026-05-01"
        assert rows[-1].payment_date == "2028-04-01"

        conn.close()
        os.unlink(db_path)

    def test_generate_regenerate_deletes_old(self):
        import tempfile, sqlite3, os
        from smefin.db import init_schema, insert_loan, get_schedule_rows
        from smefin.schedule import generate_schedule_for_loan

        db_path = tempfile.mktemp(suffix=".db")
        conn = sqlite3.connect(db_path)
        init_schema(conn)
        insert_loan({
            "id": "kur-001",
            "lender_name": "KUR BRI",
            "principal": 50_000_000.0,
            "monthly_rate": 0.012,
            "tenor_months": 24,
            "start_date": date(2026, 4, 15),
            "disbursed_amount": 50_000_000.0,
            "status": "active",
        }, conn)

        # Generate pertama
        rows1 = generate_schedule_for_loan("kur-001", conn)
        stored1 = get_schedule_rows("kur-001", conn)
        assert len(stored1) == 24

        # Generate lagi (regenerate) — harus tetap 24, bukan 48
        rows2 = generate_schedule_for_loan("kur-001", conn)
        stored2 = get_schedule_rows("kur-001", conn)
        assert len(stored2) == 24

        conn.close()
        os.unlink(db_path)

    def test_generate_nonexistent_loan_raises(self):
        import tempfile, sqlite3, os
        from smefin.db import init_schema
        from smefin.schedule import generate_schedule_for_loan

        db_path = tempfile.mktemp(suffix=".db")
        conn = sqlite3.connect(db_path)
        init_schema(conn)

        with pytest.raises(ValueError, match="not found"):
            generate_schedule_for_loan("nonexistent", conn)

        conn.close()
        os.unlink(db_path)