"""
smefin.schedule — Schedule generation + monthly outflow aggregation.
Menghubungkan calc.py (pure math) dengan db.py (storage).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from smefin.calc import compute_full_schedule, AmortizationRow


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass
class MonthlyOutflowRow:
    """
    Aggregate outflow untuk satu bulan.

    Semua field monetary adalah float. Aggregation dilakukan di
    compute_monthly_outflow sebelum return.
    """
    month: str  # ISO date string: "2026-05-01"
    total_outflow: float
    principal_outflow: float
    interest_outflow: float
    loan_count: int


@dataclass
class OutflowSummary:
    """
    Summary dari semua outflow yang di-aggregate.
    """
    total_deployed: float  # dari disbursed_amount
    total_scheduled: float
    avg_monthly_outflow: float
    highest_month: Optional[str]
    highest_outflow: float
    lowest_month: Optional[str]
    lowest_outflow: float


# ----------------------------------------------------------------------
# Schedule generation
# ----------------------------------------------------------------------


def generate_schedule_for_loan(
    loan_id: str,
    conn,
) -> list[AmortizationRow]:
    """
    Generate dan store jadwal cicilan untuk satu loan.

    Steps:
    1. Ambil loan data dari DB
    2. Hitung schedule dengan compute_full_schedule
    3. Hapus schedule lama (untuk regenerate)
    4. Insert schedule baru

    Args:
        loan_id: ID loan di DB
        conn: sqlite3 connection

    Returns:
        List[AmortizationRow] — schedule yang di-generate

    Raises:
        ValueError: jika loan_id tidak ditemukan
    """
    from smefin.db import get_loan, delete_schedule_rows, insert_schedule_rows

    loan = get_loan(loan_id, conn)
    if loan is None:
        raise ValueError(f"Loan '{loan_id}' not found in database")

    # Hitung schedule dari pure calc (tanpa DB dependency)
    rows = compute_full_schedule(
        principal=loan["principal"],
        monthly_rate=loan["monthly_rate"],
        tenor_months=loan["tenor_months"],
        start_date=loan["start_date"],
    )

    # Delete + re-insert (bukan upsert)
    delete_schedule_rows(loan_id, conn)
    insert_schedule_rows(loan_id, rows, conn)

    return rows


def generate_all_schedules(conn) -> dict[str, list[AmortizationRow]]:
    """
    Generate schedules untuk semua active loans.

    Args:
        conn: sqlite3 connection

    Returns:
        Dict[loan_id, list[AmortizationRow]] — schedule per loan
    """
    from smefin.db import get_active_loans

    loans = get_active_loans(conn)
    results: dict[str, list[AmortizationRow]] = {}

    for loan in loans:
        rows = generate_schedule_for_loan(loan["id"], conn)
        results[loan["id"]] = rows

    return results


# ----------------------------------------------------------------------
# Monthly outflow computation
# ----------------------------------------------------------------------


def compute_monthly_outflow(
    schedules: dict[str, list[AmortizationRow]],
    months: int | None = None,
) -> list[MonthlyOutflowRow]:
    """
    Aggregate outflow per bulan dari semua loan schedules.

    Setiap AmortizationRow berkontribusi ke bulan sesuai payment_date.
    Loan count dihitung sebagai distinct loan_id per bulan.

    Args:
        schedules: Dict[loan_id, list of AmortizationRow]
        months: Jika di-set, return hanya N bulan pertama (after sorting)

    Returns:
        List[MonthlyOutflowRow], di-sort oleh month (ascending)
    """
    by_month: dict[str, dict] = {}

    for loan_id, rows in schedules.items():
        for row in rows:
            month_key = row.payment_date  # ISO string: "2026-05-01"
            if month_key not in by_month:
                by_month[month_key] = {
                    "total": Decimal("0"),
                    "principal": Decimal("0"),
                    "interest": Decimal("0"),
                    "loans": set(),
                }
            by_month[month_key]["total"] += row.total_due
            by_month[month_key]["principal"] += row.principal_due
            by_month[month_key]["interest"] += row.interest_due
            by_month[month_key]["loans"].add(loan_id)

    result = [
        MonthlyOutflowRow(
            month=m,
            total_outflow=float(d["total"]),
            principal_outflow=float(d["principal"]),
            interest_outflow=float(d["interest"]),
            loan_count=len(d["loans"]),
        )
        for m, d in sorted(by_month.items())
    ]

    if months is not None:
        result = result[:months]

    return result


def compute_summary(
    outflow_rows: list[MonthlyOutflowRow],
    conn,
) -> OutflowSummary:
    """
    Compute summary dari outflow rows + loan disbursed amounts.

    total_deployed = sum dari disbursed_amount semua active loans.
    Ini adalah actual cash yang sudah keluar, bukan contractual principal.

    Args:
        outflow_rows: List[MonthlyOutflowRow] dari compute_monthly_outflow
        conn: sqlite3 connection

    Returns:
        OutflowSummary dengan semua metric di-compute
    """
    from smefin.db import get_active_loans

    active_loans = get_active_loans(conn)
    total_deployed = sum(loan["disbursed_amount"] for loan in active_loans)
    total_scheduled = sum(row.total_outflow for row in outflow_rows)
    avg_monthly = (total_scheduled / len(outflow_rows)
                   if outflow_rows else 0.0)

    if not outflow_rows:
        return OutflowSummary(
            total_deployed=total_deployed,
            total_scheduled=0.0,
            avg_monthly_outflow=0.0,
            highest_month=None,
            highest_outflow=0.0,
            lowest_month=None,
            lowest_outflow=0.0,
        )

    highest = max(outflow_rows, key=lambda r: r.total_outflow)
    lowest = min(outflow_rows, key=lambda r: r.total_outflow)

    return OutflowSummary(
        total_deployed=total_deployed,
        total_scheduled=total_scheduled,
        avg_monthly_outflow=avg_monthly,
        highest_month=highest.month,
        highest_outflow=highest.total_outflow,
        lowest_month=lowest.month,
        lowest_outflow=lowest.total_outflow,
    )