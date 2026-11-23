# Router evaluation (200 trips x 3 profiles = 600 cases)

Crash model: exposure (per-vehicle rates from TxDOT traffic counts).

Models built only from crashes through 2023; "safer" is judged on crashes from 2024 on that neither model saw: realized crashes per vehicle-mile along the route (the primary measure for the exposure model) and crashes counted within 30 m of the route (which also rewards avoiding busy roads). Seed 42.

### teen  (200 trips)
- Safest differs from fastest on **51 trips (26%)**; the other 149 get the fastest route.
- Time added, all trips: mean **+0.41 min** (95% CI +0.29 to +0.53), i.e. +2.5% of total fastest time. On the 51 changed trips: mean +1.6 min, median +1.4 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 933.2 -> safest 926.0  (mean change **-7.22**, 95% CI -23.97 to +10.92; -0.8% overall).
  - On changed trips the safest had fewer held-out crashes on **35** and more on **16** (sign test p = 0.011).
  - Serious/fatal held-out crashes: 24.81 -> 24.38 per trip (-1.7%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -22.2% overall (mean change -494.2, 95% CI -809.4 to -254.1); on changed trips safer on **44**, worse on **7** (sign test p = 0.000).
- Model risk score (circular, reference only): -14.1%.
- Baseline, a typical other route within the cap (133 trips with alternatives): -8.1% held-out crashes and +1.7 min vs the fastest. Our pick: -1.1% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 55 changed trips, +0.45 min and -0.9% held-out crashes (ours: +0.41 min, -0.8%).

### elderly  (200 trips)
- Safest differs from fastest on **66 trips (33%)**; the other 134 get the fastest route.
- Time added, all trips: mean **+0.58 min** (95% CI +0.43 to +0.75), i.e. +3.6% of total fastest time. On the 66 changed trips: mean +1.8 min, median +1.5 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 933.2 -> safest 927.2  (mean change **-6.04**, 95% CI -23.96 to +14.49; -0.6% overall).
  - On changed trips the safest had fewer held-out crashes on **46** and more on **20** (sign test p = 0.002).
  - Serious/fatal held-out crashes: 24.81 -> 24.46 per trip (-1.4%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -24.9% overall (mean change -554.4, 95% CI -902.7 to -297.1); on changed trips safer on **54**, worse on **12** (sign test p = 0.000).
- Model risk score (circular, reference only): -15.4%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.7% held-out crashes and +2.4 min vs the fastest. Our pick: -0.8% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 68 changed trips, +0.66 min and -0.4% held-out crashes (ours: +0.58 min, -0.6%).

### sensitive_passenger  (200 trips)
- Safest differs from fastest on **58 trips (29%)**; the other 142 get the fastest route.
- Time added, all trips: mean **+0.52 min** (95% CI +0.38 to +0.67), i.e. +3.2% of total fastest time. On the 58 changed trips: mean +1.8 min, median +1.5 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 933.2 -> safest 937.6  (mean change **+4.38**, 95% CI -14.97 to +24.99; +0.5% overall).
  - On changed trips the safest had fewer held-out crashes on **38** and more on **20** (sign test p = 0.025).
  - Serious/fatal held-out crashes: 24.81 -> 24.82 per trip (+0.0%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -24.3% overall (mean change -541.9, 95% CI -863.6 to -280.1); on changed trips safer on **50**, worse on **8** (sign test p = 0.000).
- Model risk score (circular, reference only): -13.5%.
- Baseline, a typical other route within the cap (144 trips with alternatives): -8.3% held-out crashes and +2.0 min vs the fastest. Our pick: +0.6% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 60 changed trips, +0.54 min and +0.4% held-out crashes (ours: +0.52 min, +0.5%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **-0.27** (95% CI -0.37 to -0.18, 150 trips with 3+ routes).
- Same check against realized per-vehicle risk: the lower model score also had the lower per-vehicle risk in **1027/1234 = 83%** of pairs (1 ties ignored).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **476/1233 = 39%** of pairs (2 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 66.27 -> safest 65.79 (route length 14.1 -> 14.1 km on average).

### By trip length (all profiles pooled)
- short: 210 cases, changed 27%, time +0.36 min, held-out crashes -1.7%
- medium: 240 cases, changed 31%, time +0.54 min, held-out crashes -0.8%
- long: 150 cases, changed 29%, time +0.65 min, held-out crashes +0.5%

Live TomTom times were available for 98% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 33,108 (2024 to latest).
