# Router evaluation (100 trips x 3 profiles = 300 cases)

Grid built from crashes through 2023; "safer" judged by held-out crashes from 2024 on within 30 m of the route. Seed 42. Test half only.

### teen  (100 trips)
- Safest differs from fastest on **25 trips (25%)**; the other 75 get the fastest route.
- Time added, all trips: mean **+0.42 min** (95% CI +0.26 to +0.60), i.e. +2.6% of total fastest time. On the 25 changed trips: mean +1.7 min, median +1.4 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 953.0 -> safest 900.6  (mean change **-52.35**, 95% CI -81.11 to -28.33; -5.5% overall).
  - On changed trips the safest had fewer held-out crashes on **25** and more on **0** (sign test p = 0.000).
  - Serious/fatal held-out crashes: 25.89 -> 23.85 per trip (-7.9%).
- Model risk score (circular, reference only): -3.4%.
- Baseline, a typical other route within the cap (68 trips with alternatives): -7.8% held-out crashes and +1.7 min vs the fastest. Our pick: -8.3% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 28 changed trips, +0.50 min and -6.3% held-out crashes (ours: +0.42 min, -5.5%).

### elderly  (100 trips)
- Safest differs from fastest on **32 trips (32%)**; the other 68 get the fastest route.
- Time added, all trips: mean **+0.65 min** (95% CI +0.42 to +0.91), i.e. +4.0% of total fastest time. On the 32 changed trips: mean +2.0 min, median +1.5 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 953.0 -> safest 898.7  (mean change **-54.22**, 95% CI -86.16 to -23.70; -5.7% overall).
  - On changed trips the safest had fewer held-out crashes on **30** and more on **2** (sign test p = 0.000).
  - Serious/fatal held-out crashes: 25.89 -> 23.93 per trip (-7.6%).
- Model risk score (circular, reference only): -4.3%.
- Baseline, a typical other route within the cap (77 trips with alternatives): -9.1% held-out crashes and +2.3 min vs the fastest. Our pick: -7.3% and +0.8 min on the same trips.
- Baseline, minimize model risk ignoring time: 36 changed trips, +0.77 min and -6.7% held-out crashes (ours: +0.65 min, -5.7%).

### sensitive_passenger  (100 trips)
- Safest differs from fastest on **23 trips (23%)**; the other 77 get the fastest route.
- Time added, all trips: mean **+0.38 min** (95% CI +0.22 to +0.56), i.e. +2.3% of total fastest time. On the 23 changed trips: mean +1.6 min, median +1.4 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 953.0 -> safest 910.0  (mean change **-42.90**, 95% CI -67.99 to -21.82; -4.5% overall).
  - On changed trips the safest had fewer held-out crashes on **22** and more on **1** (sign test p = 0.000).
  - Serious/fatal held-out crashes: 25.89 -> 24.28 per trip (-6.2%).
- Model risk score (circular, reference only): -2.9%.
- Baseline, a typical other route within the cap (71 trips with alternatives): -7.7% held-out crashes and +1.9 min vs the fastest. Our pick: -6.4% and +0.5 min on the same trips.
- Baseline, minimize model risk ignoring time: 29 changed trips, +0.54 min and -4.5% held-out crashes (ours: +0.38 min, -4.5%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **0.36** (95% CI 0.23 to 0.48, 80 trips with 3+ routes).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **423/652 = 65%** of pairs (0 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 65.44 -> safest 62.03 (route length 14.6 -> 14.5 km on average).

### By trip length (all profiles pooled)
- short: 105 cases, changed 30%, time +0.36 min, held-out crashes -8.3%
- medium: 120 cases, changed 30%, time +0.65 min, held-out crashes -6.5%
- long: 75 cases, changed 16%, time +0.38 min, held-out crashes -3.0%

Live TomTom times were available for 100% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 32,182 (2024 to latest).
