# Data refresh 2026-11-16: **ACCEPTED**

## What changed
- risk grid
- signals
- segment rates
- profile ratios

## Data
- Crashes through **2026-10-30**: 233,510 geocoded, 9,624 grid squares.
- New since the last build (crashes dated after the previous grid's data cutoff (2026-10-09)): **633** crashes.

## Forward check (the previous grid on crashes it never saw)
- 352/633 landed in the old grid's top 10% of squares = **56%** (95% interval 52%-59%; chance is 10%).

## Checks
- Similarity to previous grid: 0.9995 (need >= 0.95)
- Rolling backtest (train through 2024, 20,766 test crashes): top-10% capture **58.7%** (floor 50%, chance 10%)
- Route evaluation (200 cached trips, 32,847 held-out crashes): score/crash pair agreement **83%**
  - crash model: exposure; 'safer' = realized crashes per vehicle-mile
  - elderly: reroutes 33% of trips, +0.58 min, per-vehicle risk **-24.9%**
  - sensitive_passenger: reroutes 29% of trips, +0.52 min, per-vehicle risk **-24.3%**
  - teen: reroutes 26% of trips, +0.41 min, per-vehicle risk **-22.2%**
- Unit tests: 95 passed, 1 warning in 4.56s

_Pass/fail is decided by fixed numeric thresholds in `data/refresh.py`; see its docstring._
