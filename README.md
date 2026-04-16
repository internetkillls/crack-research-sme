# Crack Research — SME Debt Portfolio System

**Layer 1:** Cash Flow Optimizer

> Alat bantu untuk SMEs yang mengelola banyak kewajiban kredit. Menghitung jadwal cicilan, pantau working capital, dan deteksi konsentrasi risiko.

## Quick Start

```bash
# Install
pip install -e .

# Run tests
pytest tests/ -v
```

## Arsitektur

```
src/smefin/
├── calc.py      # Core: annuity formula, amortization schedule
└── __init__.py

tests/
├── conftest.py
├── test_calc.py
└── __init__.py
```

## Layer Build Order

1. **Layer 1** — Cash Flow Optimizer (ini)
2. Layer 3 — Negotiation Tracker
3. Layer 2 — Debt-to-Business Bridge

## Referensi

- Spec: `docs/superpowers/specs/2026-04-16-crack-layer1-meta-plan.md`
- Design: `30-Projects/CrackResearch-SME/spec/2026-04-15-crack-research-sme-design.md`
- Framework: [[01-Inbox/crack-research-framework]]