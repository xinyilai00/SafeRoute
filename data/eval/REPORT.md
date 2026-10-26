# Router evaluation (200 trips x 3 profiles = 600 cases)

Crash model: exposure (per-vehicle rates from TxDOT traffic counts).

Models built only from crashes through 2023; "safer" is judged on crashes from 2024 on that neither model saw: realized crashes per vehicle-mile along the route (the primary measure for the exposure model) and crashes counted within 30 m of the route (which also rewards avoiding busy roads). Seed 42.

### teen  (200 trips)
- Safest differs from fastest on **51 trips (26%)**; the other 149 get the fastest route.
- Time added, all trips: mean **+0.41 min** (95% CI +0.29 to +0.53), i.e. +2.5% of total fastest time. On the 51 changed trips: mean +1.6 min, median +1.4 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 899.1  (mean change **-7.32**, 95% CI -23.62 to +10.18; -0.8% overall).
  - On changed trips the safest had fewer held-out crashes on **35** and more on **16** (sign test p = 0.011).
  - Serious/fatal held-out crashes: 24.27 -> 23.82 per trip (-1.8%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -22.2% overall (mean change -494.5, 95% CI -809.8 to -254.4); on changed trips safer on **44**, worse on **7** (sign test p = 0.000).
- Model risk score (circular, reference only): -14.1%.
- Baseline, a typical other route within the cap (133 trips with alternatives): -8.2% held-out crashes and +1.7 min vs the fastest. Our pick: -1.2% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 56 changed trips, +0.46 min and -0.9% held-out crashes (ours: +0.41 min, -0.8%).

### elderly  (200 trips)
- Safest differs from fastest on **67 trips (34%)**; the other 133 get the fastest route.
- Time added, all trips: mean **+0.58 min** (95% CI +0.43 to +0.75), i.e. +3.6% of total fastest time. On the 67 changed trips: mean +1.7 min, median +1.4 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 900.0  (mean change **-6.46**, 95% CI -23.61 to +13.37; -0.7% overall).
  - On changed trips the safest had fewer held-out crashes on **47** and more on **20** (sign test p = 0.001).
  - Serious/fatal held-out crashes: 24.27 -> 23.91 per trip (-1.5%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -24.9% overall (mean change -554.6, 95% CI -902.8 to -297.3); on changed trips safer on **54**, worse on **13** (sign test p = 0.000).
- Model risk score (circular, reference only): -15.4%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -0.9% and +0.8 min on the same trips.
- Baseline, minimize model risk ignoring time: 69 changed trips, +0.66 min and -0.5% held-out crashes (ours: +0.58 min, -0.7%).

### sensitive_passenger  (200 trips)
- Safest differs from fastest on **58 trips (29%)**; the other 142 get the fastest route.
- Time added, all trips: mean **+0.52 min** (95% CI +0.38 to +0.67), i.e. +3.2% of total fastest time. On the 58 changed trips: mean +1.8 min, median +1.5 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 910.3  (mean change **+3.83**, 95% CI -14.78 to +23.71; +0.4% overall).
  - On changed trips the safest had fewer held-out crashes on **38** and more on **20** (sign test p = 0.025).
  - Serious/fatal held-out crashes: 24.27 -> 24.25 per trip (-0.1%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -24.4% overall (mean change -542.3, 95% CI -864.0 to -280.1); on changed trips safer on **50**, worse on **8** (sign test p = 0.000).
- Model risk score (circular, reference only): -13.5%.
- Baseline, a typical other route within the cap (144 trips with alternatives): -8.3% held-out crashes and +2.0 min vs the fastest. Our pick: +0.6% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 60 changed trips, +0.54 min and +0.4% held-out crashes (ours: +0.52 min, +0.4%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **-0.27** (95% CI -0.37 to -0.18, 150 trips with 3+ routes).
- Same check against realized per-vehicle risk: the lower model score also had the lower per-vehicle risk in **1027/1234 = 83%** of pairs (1 ties ignored).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **476/1233 = 39%** of pairs (2 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 64.36 -> safest 63.88 (route length 14.1 -> 14.1 km on average).

### By trip length (all profiles pooled)
- short: 210 cases, changed 27%, time +0.36 min, held-out crashes -1.8%
- medium: 240 cases, changed 31%, time +0.54 min, held-out crashes -0.8%
- long: 150 cases, changed 29%, time +0.65 min, held-out crashes +0.5%

Live TomTom times were available for 98% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 32,182 (2024 to latest).
