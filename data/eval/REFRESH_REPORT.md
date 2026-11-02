# Data refresh 2026-11-02: **ACCEPTED**

## What changed
- risk grid
- signals
- segment rates
- profile ratios

## Data
- Crashes through **2026-10-16**: 233,071 geocoded, 9,622 grid squares.
- New since the last build (crashes dated after the previous grid's data cutoff (2026-10-09)): **210** crashes.

## Forward check (the previous grid on crashes it never saw)
- 120/210 landed in the old grid's top 10% of squares = **57%** (95% interval 50%-64%; chance is 10%).

## Checks
- Similarity to previous grid: 0.9999 (need >= 0.95)
- Rolling backtest (train through 2024, 20,325 test crashes): top-10% capture **58.8%** (floor 50%, chance 10%)
- Route evaluation (200 cached trips, 32,406 held-out crashes): score/crash pair agreement **83%**
  - crash model: exposure; 'safer' = realized crashes per vehicle-mile
  - elderly: reroutes 34% of trips, +0.58 min, per-vehicle risk **-24.9%**
  - sensitive_passenger: reroutes 29% of trips, +0.52 min, per-vehicle risk **-24.4%**
  - teen: reroutes 26% of trips, +0.41 min, per-vehicle risk **-22.2%**
- Unit tests: 95 passed, 2 warnings in 4.00s

_Pass/fail is decided by fixed numeric thresholds in `data/refresh.py`; see its docstring._
