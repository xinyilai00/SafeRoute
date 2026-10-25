# Router evaluation (200 trips x 3 profiles = 600 cases)

Grid built from crashes through 2023; "safer" judged by held-out crashes from 2024 on within 30 m of the route. Seed 42.

### teen  (200 trips)
- Safest differs from fastest on **35 trips (18%)**; the other 165 get the fastest route.
- Time added, all trips: mean **+0.23 min** (95% CI +0.14 to +0.32), i.e. +1.4% of total fastest time. On the 35 changed trips: mean +1.3 min, median +1.0 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 869.2  (mean change **-37.26**, 95% CI -56.61 to -21.57; -4.1% overall).
  - On changed trips the safest had fewer held-out crashes on **34** and more on **1** (sign test p = 0.000).
  - Serious/fatal held-out crashes: 24.27 -> 23.07 per trip (-4.9%).
- Model risk score (circular, reference only): -2.7%.
- Baseline, a typical other route within the cap (133 trips with alternatives): -8.2% held-out crashes and +1.7 min vs the fastest. Our pick: -6.0% and +0.3 min on the same trips.
- Baseline, minimize model risk ignoring time: 54 changed trips, +0.45 min and -5.7% held-out crashes (ours: +0.23 min, -4.1%).

### elderly  (200 trips)
- Safest differs from fastest on **45 trips (22%)**; the other 155 get the fastest route.
- Time added, all trips: mean **+0.37 min** (95% CI +0.26 to +0.49), i.e. +2.3% of total fastest time. On the 45 changed trips: mean +1.6 min, median +1.3 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 862.7  (mean change **-43.75**, 95% CI -63.50 to -26.64; -4.8% overall).
  - On changed trips the safest had fewer held-out crashes on **43** and more on **2** (sign test p = 0.000).
  - Serious/fatal held-out crashes: 24.27 -> 22.93 per trip (-5.5%).
- Model risk score (circular, reference only): -3.4%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -6.0% and +0.5 min on the same trips.
- Baseline, minimize model risk ignoring time: 68 changed trips, +0.67 min and -6.0% held-out crashes (ours: +0.37 min, -4.8%).

### sensitive_passenger  (200 trips)
- Safest differs from fastest on **39 trips (20%)**; the other 161 get the fastest route.
- Time added, all trips: mean **+0.28 min** (95% CI +0.18 to +0.38), i.e. +1.7% of total fastest time. On the 39 changed trips: mean +1.4 min, median +1.1 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 872.0  (mean change **-34.42**, 95% CI -52.21 to -19.86; -3.8% overall).
  - On changed trips the safest had fewer held-out crashes on **36** and more on **3** (sign test p = 0.000).
  - Serious/fatal held-out crashes: 24.27 -> 23.07 per trip (-4.9%).
- Model risk score (circular, reference only): -2.5%.
- Baseline, a typical other route within the cap (144 trips with alternatives): -8.3% held-out crashes and +2.0 min vs the fastest. Our pick: -5.2% and +0.4 min on the same trips.
- Baseline, minimize model risk ignoring time: 60 changed trips, +0.54 min and -4.4% held-out crashes (ours: +0.28 min, -3.8%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **0.29** (95% CI 0.19 to 0.38, 150 trips with 3+ routes).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **775/1233 = 63%** of pairs (2 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 64.36 -> safest 62.03 (route length 14.1 -> 14.0 km on average).

### By trip length (all profiles pooled)
- short: 210 cases, changed 21%, time +0.21 min, held-out crashes -6.6%
- medium: 240 cases, changed 24%, time +0.42 min, held-out crashes -4.5%
- long: 150 cases, changed 12%, time +0.20 min, held-out crashes -3.2%

Live TomTom times were available for 98% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 32,182 (2024 to latest).
