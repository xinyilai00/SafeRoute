# Data refresh 2026-10-25: **ACCEPTED**

## Data
- Crashes through **2026-10-09**: 232,847 geocoded, 9,622 grid squares.
- New since the last build (crashes dated after the previous grid's data cutoff (2026-10-09)): **0** crashes.

## Checks
- Similarity to previous grid: 1.0000 (need >= 0.95)
- Rolling backtest (train through 2024, 20,101 test crashes): top-10% capture **58.9%** (floor 50%, chance 10%)
- Route evaluation (200 cached trips, 32,182 held-out crashes): score/crash pair agreement **63%**
  - elderly: reroutes 22% of trips, +0.37 min, held-out crashes **-4.8%**
  - sensitive_passenger: reroutes 20% of trips, +0.28 min, held-out crashes **-3.8%**
  - teen: reroutes 18% of trips, +0.23 min, held-out crashes **-4.1%**
- Unit tests: 71 passed, 2 warnings in 5.75s

_Pass/fail is decided by fixed numeric thresholds in `data/refresh.py`; see its docstring._
