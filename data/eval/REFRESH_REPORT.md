# Data refresh 2026-10-25: **ACCEPTED**

## Data
- Crashes through **2026-10-09**: 232,847 geocoded, 9,622 grid squares.
- New since the last build (crash ids not present in the previous download): **0** crashes.

## Checks
- Similarity to previous grid: 1.0000 (need >= 0.95)
- Rolling backtest (train through 2024, 20,101 test crashes): top-10% capture **58.9%** (floor 50%, chance 10%)
- Route evaluation (200 cached trips, 32,182 held-out crashes): score/crash pair agreement **82%**
  - crash model: exposure; 'safer' = realized crashes per vehicle-mile
  - elderly: reroutes 28% of trips, +0.49 min, per-vehicle risk **-23.4%**
  - sensitive_passenger: reroutes 26% of trips, +0.44 min, per-vehicle risk **-22.7%**
  - teen: reroutes 22% of trips, +0.33 min, per-vehicle risk **-20.3%**
- Unit tests: 94 passed, 2 warnings in 3.71s

_Pass/fail is decided by fixed numeric thresholds in `data/refresh.py`; see its docstring._
