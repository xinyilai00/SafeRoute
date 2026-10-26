# Data refresh 2026-10-26: **ACCEPTED**

## What changed
- segment rates

## Data
- Crashes through **2026-10-09**: 232,847 geocoded, 9,622 grid squares.
- New since the last build (crashes dated after the previous grid's data cutoff (2026-10-09)): **0** crashes.

## Checks
- Similarity to previous grid: 1.0000 (need >= 0.95)
- Rolling backtest (train through 2024, 20,101 test crashes): top-10% capture **58.9%** (floor 50%, chance 10%)
- Route evaluation (200 cached trips, 32,182 held-out crashes): score/crash pair agreement **83%**
  - crash model: exposure; 'safer' = realized crashes per vehicle-mile
  - elderly: reroutes 34% of trips, +0.58 min, per-vehicle risk **-24.9%**
  - sensitive_passenger: reroutes 29% of trips, +0.52 min, per-vehicle risk **-24.4%**
  - teen: reroutes 26% of trips, +0.41 min, per-vehicle risk **-22.2%**
- Unit tests: 95 passed, 2 warnings in 6.37s

_Pass/fail is decided by fixed numeric thresholds in `data/refresh.py`; see its docstring._
