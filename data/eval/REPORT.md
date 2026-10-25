# Router evaluation (200 trips x 3 profiles = 600 cases)

Crash model: exposure (per-vehicle rates from TxDOT traffic counts).

Models built only from crashes through 2023; "safer" is judged on crashes from 2024 on that neither model saw: realized crashes per vehicle-mile along the route (the primary measure for the exposure model) and crashes counted within 30 m of the route (which also rewards avoiding busy roads). Seed 42.

### teen  (200 trips)
- Safest differs from fastest on **51 trips (26%)**; the other 149 get the fastest route.
- Time added, all trips: mean **+0.47 min** (95% CI +0.33 to +0.62), i.e. +2.9% of total fastest time. On the 51 changed trips: mean +1.8 min, median +1.6 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 902.2  (mean change **-4.25**, 95% CI -21.14 to +14.81; -0.5% overall).
  - On changed trips the safest had fewer held-out crashes on **36** and more on **15** (sign test p = 0.005).
  - Serious/fatal held-out crashes: 24.27 -> 23.82 per trip (-1.8%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -23.3% overall (mean change -519.2, 95% CI -848.5 to -266.2); on changed trips safer on **45**, worse on **6** (sign test p = 0.000).
- Model risk score (circular, reference only): -12.4%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -0.6% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 57 changed trips, +0.58 min and -0.4% held-out crashes (ours: +0.47 min, -0.5%).

### elderly  (200 trips)
- Safest differs from fastest on **55 trips (28%)**; the other 145 get the fastest route.
- Time added, all trips: mean **+0.49 min** (95% CI +0.35 to +0.65), i.e. +3.0% of total fastest time. On the 55 changed trips: mean +1.8 min, median +1.4 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 902.3  (mean change **-4.17**, 95% CI -21.16 to +15.32; -0.5% overall).
  - On changed trips the safest had fewer held-out crashes on **39** and more on **16** (sign test p = 0.003).
  - Serious/fatal held-out crashes: 24.27 -> 23.95 per trip (-1.3%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -23.4% overall (mean change -520.4, 95% CI -866.3 to -268.1); on changed trips safer on **48**, worse on **7** (sign test p = 0.000).
- Model risk score (circular, reference only): -12.7%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -0.6% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 64 changed trips, +0.65 min and -0.4% held-out crashes (ours: +0.49 min, -0.5%).

### sensitive_passenger  (200 trips)
- Safest differs from fastest on **53 trips (26%)**; the other 147 get the fastest route.
- Time added, all trips: mean **+0.44 min** (95% CI +0.31 to +0.59), i.e. +2.7% of total fastest time. On the 53 changed trips: mean +1.7 min, median +1.3 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 910.1  (mean change **+3.62**, 95% CI -15.05 to +23.39; +0.4% overall).
  - On changed trips the safest had fewer held-out crashes on **34** and more on **19** (sign test p = 0.053).
  - Serious/fatal held-out crashes: 24.27 -> 24.17 per trip (-0.4%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -22.7% overall (mean change -505.7, 95% CI -831.4 to -251.7); on changed trips safer on **45**, worse on **8** (sign test p = 0.000).
- Model risk score (circular, reference only): -10.6%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: +0.5% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 59 changed trips, +0.55 min and +0.0% held-out crashes (ours: +0.44 min, +0.4%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **-0.28** (95% CI -0.37 to -0.18, 150 trips with 3+ routes).
- Same check against realized per-vehicle risk: the lower model score also had the lower per-vehicle risk in **1013/1234 = 82%** of pairs (1 ties ignored).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **474/1233 = 38%** of pairs (2 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 64.36 -> safest 64.11 (route length 14.1 -> 14.1 km on average).

### By trip length (all profiles pooled)
- short: 210 cases, changed 25%, time +0.37 min, held-out crashes -2.0%
- medium: 240 cases, changed 29%, time +0.49 min, held-out crashes -0.6%
- long: 150 cases, changed 25%, time +0.57 min, held-out crashes +0.7%

Live TomTom times were available for 98% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 32,182 (2024 to latest).
