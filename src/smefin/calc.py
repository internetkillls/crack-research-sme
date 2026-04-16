"""
smefin.calc — Core annuity calculation engine.
Tanpa I/O, tanpa DB. Fungsi murni dengan typed inputs/outputs.

Semua kalkulasi finansial menggunakan Decimal di internal path
untuk menghindari floating-point error yang akumulatif.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

_DECIMAL_TWO = Decimal("0.01")


# ----------------------------------------------------------------------
# Rounding utility
# ----------------------------------------------------------------------


def _round_currency(amount: Decimal | float) -> Decimal:
    """Kuantisasi ke Rupiah terdekat (2 desimal), pakai ROUND_HALF_UP."""
    if isinstance(amount, float):
        amount = Decimal(str(amount))
    return amount.quantize(_DECIMAL_TWO, rounding=ROUND_HALF_UP)


# ----------------------------------------------------------------------
# Month arithmetic (zero-dependency)
# ----------------------------------------------------------------------


def add_months(ref_date: date, months: int) -> date:
    """
    Tambahkan N bulan ke sebuah date, tanpa library eksternal.

    End-of-month behavior: jika tanggal asli adalah akhir bulan
    (mis. 31 Jan → tidak ada 31 Feb), hasil menggunakan hari
    terakhir bulan tujuan. Ini konsisten dengan perilaku
    python-dateutil relativedelta.

    Args:
        ref_date: tanggal referensi
        months: jumlah bulan yang ditambahkan (bisa negatif)

    Returns:
        Tanggal baru setelah penambahan bulan

    Examples:
        >>> add_months(date(2026, 1, 15), 1)
        date(2026, 2, 15)
        >>> add_months(date(2026, 1, 31), 1)
        date(2026, 2, 28)
        >>> add_months(date(2026, 12, 15), 1)
        date(2027, 1, 15)
        >>> add_months(date(2026, 3, 31), 1)
        date(2026, 4, 30)
    """
    month = ref_date.month + months
    year = ref_date.year

    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1

    # Cari hari terakhir bulan tujuan
    days_in_month = [
        31,  # Jan
        28,  # Feb (default)
        31,  # Mar
        30,  # Apr
        31,  # May
        30,  # Jun
        31,  # Jul
        31,  # Aug
        30,  # Sep
        31,  # Oct
        30,  # Nov
        31,  # Dec
    ]

    # Leap year untuk Februari
    if month == 2:
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            last_day = 29
        else:
            last_day = 28
    else:
        last_day = days_in_month[month - 1]

    # Kalau tanggal asli lebih besar dari hari terakhir bulan tujuan,
    # gunakan hari terakhir bulan tujuan (end-of-month anchor)
    day = ref_date.day if ref_date.day <= last_day else last_day

    return date(year, month, day)


# ----------------------------------------------------------------------
# Dataclass
# ----------------------------------------------------------------------


@dataclass
class AmortizationRow:
    """
    Satu baris dari tabel amortisasi.

    Semua field monetary adalah Decimal (bukan float) untuk presisi
    finansial. payment_date string dalam format ISO 8601 (YYYY-MM-DD).
    """
    month_number: int
    payment_date: str
    interest_due: Decimal
    principal_due: Decimal
    total_due: Decimal
    balance_remaining: Decimal


# ----------------------------------------------------------------------
# Core calculation functions
# ----------------------------------------------------------------------


def compute_monthly_payment(
    principal: float,
    monthly_rate: float,
    tenor_months: int
) -> float:
    """
    Hitung cicilan bulanan tetap menggunakan rumus anuitas.

    M = P * r / (1 - (1 + r)^-n)

    Args:
        principal: jumlah pinjaman (Rp)
        monthly_rate: suku bunga per bulan (0.012 = 14.4% annual)
        tenor_months: jumlah bulan

    Returns:
        Cicilan bulanan tetap (Rp)

    Raises:
        ValueError: jika monthly_rate negatif atau tenor_months < 1

    Edge cases:
        - rate == 0 → Decimal division (pinjaman tanpa bunga/subsidi)
        - rate < 0 → raise ValueError
        - tenor < 1 → raise ValueError
    """
    if monthly_rate < 0:
        raise ValueError("rate must be non-negative")
    if tenor_months < 1:
        raise ValueError("tenor must be at least 1")

    if monthly_rate == 0.0:
        # Zero rate: pakai Decimal agar hasil exact (tidak ada floating-point)
        d_principal = Decimal(str(principal))
        d_payment = (d_principal / Decimal(tenor_months)).quantize(
            _DECIMAL_TWO, rounding=ROUND_HALF_UP
        )
        return float(d_payment)

    # Rate > 0: gunakan Decimal untuk akurasi
    d_principal = Decimal(str(principal))
    d_rate = Decimal(str(monthly_rate))
    d_n = Decimal(tenor_months)

    d_factor = (Decimal(1) + d_rate) ** (-d_n)
    d_payment = d_principal * d_rate / (Decimal(1) - d_factor)
    d_payment = d_payment.quantize(_DECIMAL_TWO, rounding=ROUND_HALF_UP)

    return float(d_payment)


def compute_amortization_row(
    balance: float,
    monthly_payment: float,
    monthly_rate: float,
    month_number: int,
    payment_date: str,
) -> AmortizationRow:
    """
    Hitung satu baris tabel amortisasi dari saldo terkini.

    Args:
        balance: saldo pinjaman sebelum pembayaran ini
        monthly_payment: cicilan bulanan tetap
        monthly_rate: suku bunga per bulan
        month_number: nomor bulan (1-based)
        payment_date: tanggal pembayaran dalam format YYYY-MM-DD

    Returns:
        AmortizationRow dengan semua komponen breakdown

    Edge cases:
        - balance < principal (final payment kurang dari full principal)
          → balance_remaining = 0.0, principal_due = balance.
          Final payment mungkin sedikit kurang dari monthly_payment.
    """
    d_balance = Decimal(str(balance))
    d_payment = Decimal(str(monthly_payment))
    d_rate = Decimal(str(monthly_rate))

    d_interest = _round_currency(d_balance * d_rate)
    d_principal = d_payment - d_interest

    # Edge case: final payment — principal portion may exceed balance
    if d_principal > d_balance:
        d_principal = d_balance
        d_interest = d_balance

    d_balance_remaining = max(Decimal("0"), d_balance - d_principal)

    return AmortizationRow(
        month_number=month_number,
        payment_date=payment_date,
        interest_due=d_interest,
        principal_due=d_principal,
        total_due=d_payment,
        balance_remaining=d_balance_remaining,
    )


def compute_full_schedule(
    principal: float,
    monthly_rate: float,
    tenor_months: int,
    start_date: date,
) -> List[AmortizationRow]:
    """
    Generate tabel amortisasi lengkap untuk satu pinjaman.

    Mengikuti logika first-of-next-month: jika start_date bukan
    tanggal 1, pembayaran pertama di tanggal 1 bulan berikutnya.
    Tidak ada prorated payment di v1 — pembayaran pertama penuh.

    Args:
        principal: jumlah pinjaman
        monthly_rate: suku bunga per bulan
        tenor_months: jumlah bulan
        start_date: tanggal mulai pinjaman

    Returns:
        List[AmortizationRow] — satu baris per bulan

    Raises:
        ValueError: jika principal <= 0
    """
    if principal <= 0:
        raise ValueError("principal must be positive")

    monthly_payment = compute_monthly_payment(principal, monthly_rate, tenor_months)

    # First payment date: first of month on or after start_date
    if start_date.day == 1:
        first_payment = start_date
    else:
        first_payment = add_months(date(start_date.year, start_date.month, 1), 1)

    balance = Decimal(str(principal))
    d_payment = Decimal(str(monthly_payment))
    d_rate = Decimal(str(monthly_rate))

    rows: List[AmortizationRow] = []

    for m in range(1, tenor_months + 1):
        payment_date = add_months(first_payment, m - 1)

        d_interest = _round_currency(balance * d_rate)
        d_principal = d_payment - d_interest

        # Final payment: gunakan sisa saldo sebagai principal dan total.
        # Ini menjamin balance_remaining = 0 di baris terakhir.
        if m == tenor_months or d_principal > balance:
            d_principal = balance
            d_interest = balance
            d_payment = balance  # total_due = principal (no rounding)
            d_balance_remaining = Decimal("0")
        else:
            d_balance_remaining = max(Decimal("0"), balance - d_principal)

        rows.append(AmortizationRow(
            month_number=m,
            payment_date=payment_date.isoformat(),
            interest_due=d_interest,
            principal_due=d_principal,
            total_due=d_payment,
            balance_remaining=d_balance_remaining,
        ))

        balance = d_balance_remaining

    return rows