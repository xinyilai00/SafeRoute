# Router evaluation (200 trips x 3 profiles = 600 cases)

Crash model: exposure (per-vehicle rates from TxDOT traffic counts).

Models built only from crashes through 2023; "safer" is judged on crashes from 2024 on that neither model saw: realized crashes per vehicle-mile along the route (the primary measure for the exposure model) and crashes counted within 30 m of the route (which also rewards avoiding busy roads). Seed 42.

### teen  (200 trips)
- Safest differs from fastest on **44 trips (22%)**; the other 156 get the fastest route.
- Time added, all trips: mean **+0.33 min** (95% CI +0.22 to +0.45), i.e. +2.0% of total fastest time. On the 44 changed trips: mean +1.5 min, median +1.2 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 900.9  (mean change **-5.54**, 95% CI -21.09 to +11.61; -0.6% overall).
  - On changed trips the safest had fewer held-out crashes on **31** and more on **13** (sign test p = 0.010).
  - Serious/fatal held-out crashes: 24.27 -> 23.75 per trip (-2.1%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -20.3% overall (mean change -451.4, 95% CI -768.5 to -217.9); on changed trips safer on **39**, worse on **5** (sign test p = 0.000).
- Model risk score (circular, reference only): -10.6%.
- Baseline, a typical other route within the cap (133 trips with alternatives): -8.2% held-out crashes and +1.7 min vs the fastest. Our pick: -0.9% and +0.5 min on the same trips.
- Baseline, minimize model risk ignoring time: 52 changed trips, +0.43 min and -0.7% held-out crashes (ours: +0.33 min, -0.6%).

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
- Baseline, a typical other route within the cap (144 trips with alternatives): -8.3% held-out crashes and +2.0 min vs the fastest. Our pick: +0.5% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 58 changed trips, +0.52 min and +0.2% held-out crashes (ours: +0.44 min, +0.4%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **-0.28** (95% CI -0.37 to -0.18, 150 trips with 3+ routes).
- Same check against realized per-vehicle risk: the lower model score also had the lower per-vehicle risk in **1013/1234 = 82%** of pairs (1 ties ignored).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **474/1233 = 38%** of pairs (2 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 64.36 -> safest 64.06 (route length 14.1 -> 14.1 km on average).

### By trip length (all profiles pooled)
- short: 210 cases, changed 24%, time +0.31 min, held-out crashes -2.0%
- medium: 240 cases, changed 28%, time +0.45 min, held-out crashes -0.4%
- long: 150 cases, changed 24%, time +0.53 min, held-out crashes +0.5%

Live TomTom times were available for 98% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 32,182 (2024 to latest).
