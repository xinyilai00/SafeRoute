# Router evaluation (200 trips x 3 profiles = 600 cases)

Crash model: exposure (per-vehicle rates from TxDOT traffic counts).

Models built only from crashes through 2023; "safer" is judged on crashes from 2024 on that neither model saw: realized crashes per vehicle-mile along the route (the primary measure for the exposure model) and crashes counted within 30 m of the route (which also rewards avoiding busy roads). Seed 42.

### teen  (200 trips)
- Safest differs from fastest on **48 trips (24%)**; the other 152 get the fastest route.
- Time added, all trips: mean **+0.37 min** (95% CI +0.26 to +0.50), i.e. +2.3% of total fastest time. On the 48 changed trips: mean +1.6 min, median +1.3 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 899.4  (mean change **-7.02**, 95% CI -23.03 to +10.27; -0.8% overall).
  - On changed trips the safest had fewer held-out crashes on **34** and more on **14** (sign test p = 0.006).
  - Serious/fatal held-out crashes: 24.27 -> 23.74 per trip (-2.2%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -20.9% overall (mean change -466.3, 95% CI -784.2 to -230.5); on changed trips safer on **42**, worse on **6** (sign test p = 0.000).
- Model risk score (circular, reference only): -11.0%.
- Baseline, a typical other route within the cap (133 trips with alternatives): -8.2% held-out crashes and +1.7 min vs the fastest. Our pick: -1.1% and +0.6 min on the same trips.
- Baseline, minimize model risk ignoring time: 52 changed trips, +0.43 min and -0.7% held-out crashes (ours: +0.37 min, -0.8%).

### elderly  (200 trips)
- Safest differs from fastest on **64 trips (32%)**; the other 136 get the fastest route.
- Time added, all trips: mean **+0.56 min** (95% CI +0.42 to +0.73), i.e. +3.4% of total fastest time. On the 64 changed trips: mean +1.8 min, median +1.6 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 899.5  (mean change **-6.91**, 95% CI -24.09 to +12.97; -0.8% overall).
  - On changed trips the safest had fewer held-out crashes on **46** and more on **18** (sign test p = 0.001).
  - Serious/fatal held-out crashes: 24.27 -> 23.88 per trip (-1.6%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -24.4% overall (mean change -544.3, 95% CI -891.0 to -289.1); on changed trips safer on **52**, worse on **12** (sign test p = 0.000).
- Model risk score (circular, reference only): -12.5%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -0.9% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 69 changed trips, +0.65 min and -0.4% held-out crashes (ours: +0.56 min, -0.8%).

### sensitive_passenger  (200 trips)
- Safest differs from fastest on **56 trips (28%)**; the other 144 get the fastest route.
- Time added, all trips: mean **+0.48 min** (95% CI +0.34 to +0.63), i.e. +3.0% of total fastest time. On the 56 changed trips: mean +1.7 min, median +1.4 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 908.0  (mean change **+1.57**, 95% CI -17.17 to +21.70; +0.2% overall).
  - On changed trips the safest had fewer held-out crashes on **37** and more on **19** (sign test p = 0.022).
  - Serious/fatal held-out crashes: 24.27 -> 24.07 per trip (-0.8%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -22.9% overall (mean change -509.9, 95% CI -835.8 to -255.6); on changed trips safer on **48**, worse on **8** (sign test p = 0.000).
- Model risk score (circular, reference only): -10.6%.
- Baseline, a typical other route within the cap (144 trips with alternatives): -8.3% held-out crashes and +2.0 min vs the fastest. Our pick: +0.2% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 58 changed trips, +0.52 min and +0.2% held-out crashes (ours: +0.48 min, +0.2%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **-0.28** (95% CI -0.37 to -0.18, 150 trips with 3+ routes).
- Same check against realized per-vehicle risk: the lower model score also had the lower per-vehicle risk in **1013/1234 = 82%** of pairs (1 ties ignored).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **474/1233 = 38%** of pairs (2 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 64.36 -> safest 63.90 (route length 14.1 -> 14.1 km on average).

### By trip length (all profiles pooled)
- short: 210 cases, changed 26%, time +0.35 min, held-out crashes -2.1%
- medium: 240 cases, changed 30%, time +0.52 min, held-out crashes -0.8%
- long: 150 cases, changed 27%, time +0.57 min, held-out crashes +0.4%

Live TomTom times were available for 98% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 32,182 (2024 to latest).
