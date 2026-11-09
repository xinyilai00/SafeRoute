# Data refresh 2026-11-09: **ACCEPTED**

## What changed
- risk grid
- signals
- segment rates
- profile ratios

## Data
- Crashes through **2026-10-23**: 233,306 geocoded, 9,624 grid squares.
- New since the last build (crashes dated after the previous grid's data cutoff (2026-10-09)): **430** crashes.

## Forward check (the previous grid on crashes it never saw)
- 246/430 landed in the old grid's top 10% of squares = **57%** (95% interval 52%-62%; chance is 10%).

## Checks
- Similarity to previous grid: 0.9998 (need >= 0.95)
- Rolling backtest (train through 2024, 20,561 test crashes): top-10% capture **58.8%** (floor 50%, chance 10%)
- Route evaluation (200 cached trips, 32,642 held-out crashes): score/crash pair agreement **83%**
  - crash model: exposure; 'safer' = realized crashes per vehicle-mile
  - elderly: reroutes 34% of trips, +0.58 min, per-vehicle risk **-24.9%**
  - sensitive_passenger: reroutes 29% of trips, +0.52 min, per-vehicle risk **-24.3%**
  - teen: reroutes 26% of trips, +0.41 min, per-vehicle risk **-22.2%**
- Unit tests: 95 passed, 1 warning in 5.20s

_Pass/fail is decided by fixed numeric thresholds in `data/refresh.py`; see its docstring._
