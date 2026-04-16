"""
smefin.db — SQLite database helpers.
Semua operasi DB terpusat di sini. Tidak ada raw SQL di module lain.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional


# ----------------------------------------------------------------------
# Schema initialization
# ----------------------------------------------------------------------


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize all tables. Safe to call on existing DB (IF NOT EXISTS)."""
    conn.row_factory = sqlite3.Row  # Enable column-by-name access
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS loans (
            id TEXT PRIMARY KEY,
            lender_name TEXT NOT NULL,
            principal REAL NOT NULL,
            monthly_rate REAL NOT NULL,
            tenor_months INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            disbursed_amount REAL NOT NULL,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS payment_schedule (
            loan_id TEXT NOT NULL,
            month_number INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            principal_due REAL NOT NULL,
            interest_due REAL NOT NULL,
            total_due REAL NOT NULL,
            balance_remaining REAL NOT NULL,
            PRIMARY KEY (loan_id, month_number),
            FOREIGN KEY (loan_id) REFERENCES loans(id)
        );

        CREATE TABLE IF NOT EXISTS payment_events (
            id TEXT PRIMARY KEY,
            loan_id TEXT NOT NULL,
            event_date TEXT NOT NULL,
            amount_paid REAL NOT NULL,
            event_type TEXT,
            FOREIGN KEY (loan_id) REFERENCES loans(id)
        );

        CREATE TABLE IF NOT EXISTS settlements (
            loan_id TEXT PRIMARY KEY,
            negotiation_start TEXT,
            settlement_amount REAL,
            original_outstanding REAL,
            discount_pct REAL,
            status TEXT,
            FOREIGN KEY (loan_id) REFERENCES loans(id)
        );
    """)
    conn.commit()


# ----------------------------------------------------------------------
# Loan helpers
# ----------------------------------------------------------------------


def insert_loan(loan: dict, conn: sqlite3.Connection) -> None:
    """Insert a loan row. Raises if id already exists."""
    conn.execute("""
        INSERT INTO loans (id, lender_name, principal, monthly_rate, tenor_months,
                          start_date, disbursed_amount, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        loan["id"],
        loan["lender_name"],
        float(loan["principal"]),
        float(loan["monthly_rate"]),
        int(loan["tenor_months"]),
        str(loan["start_date"]),
        float(loan["disbursed_amount"]),
        loan.get("status", "active"),
    ))
    conn.commit()


def get_loan(loan_id: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Return loan dict or None if not found."""
    row = conn.execute(
        "SELECT * FROM loans WHERE id = ?", (loan_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_loan(row)


def get_active_loans(conn: sqlite3.Connection) -> list[dict]:
    """Return all loans with status = 'active'."""
    rows = conn.execute(
        "SELECT * FROM loans WHERE status = 'active'"
    ).fetchall()
    return [_row_to_loan(r) for r in rows]


def _row_to_loan(row: sqlite3.Row) -> dict:
    """Convert DB row to loan dict with proper types."""
    return {
        "id": row["id"],
        "lender_name": row["lender_name"],
        "principal": row["principal"],
        "monthly_rate": row["monthly_rate"],
        "tenor_months": row["tenor_months"],
        "start_date": date.fromisoformat(row["start_date"]),
        "disbursed_amount": row["disbursed_amount"],
        "status": row["status"],
    }


# ----------------------------------------------------------------------
# Schedule helpers
# ----------------------------------------------------------------------


def delete_schedule_rows(loan_id: str, conn: sqlite3.Connection) -> None:
    """Delete all payment_schedule rows for a loan (for regeneration)."""
    conn.execute(
        "DELETE FROM payment_schedule WHERE loan_id = ?", (loan_id,)
    )


def insert_schedule_rows(
    loan_id: str,
    rows: list,
    conn: sqlite3.Connection,
) -> None:
    """Bulk insert AmortizationRow list into payment_schedule."""
    data = [
        (
            loan_id,
            int(row.month_number),
            row.payment_date,
            float(row.principal_due),
            float(row.interest_due),
            float(row.total_due),
            float(row.balance_remaining),
        )
        for row in rows
    ]
    conn.executemany("""
        INSERT INTO payment_schedule
            (loan_id, month_number, payment_date, principal_due,
             interest_due, total_due, balance_remaining)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, data)
    conn.commit()


def get_schedule_rows(
    loan_id: str,
    conn: sqlite3.Connection,
) -> list[dict]:
    """Return all payment_schedule rows for a loan, ordered by month_number."""
    rows = conn.execute(
        "SELECT * FROM payment_schedule WHERE loan_id = ? ORDER BY month_number",
        (loan_id,)
    ).fetchall()
    return [_row_to_schedule(r) for r in rows]


def _row_to_schedule(row: sqlite3.Row) -> dict:
    return {
        "loan_id": row["loan_id"],
        "month_number": row["month_number"],
        "payment_date": row["payment_date"],
        "principal_due": row["principal_due"],
        "interest_due": row["interest_due"],
        "total_due": row["total_due"],
        "balance_remaining": row["balance_remaining"],
    }