# Router evaluation (200 trips x 3 profiles = 600 cases)

Crash model: exposure (per-vehicle rates from TxDOT traffic counts).

Models built only from crashes through 2023; "safer" is judged on crashes from 2024 on that neither model saw: realized crashes per vehicle-mile along the route (the primary measure for the exposure model) and crashes counted within 30 m of the route (which also rewards avoiding busy roads). Seed 42.

### teen  (200 trips)
- Safest differs from fastest on **54 trips (27%)**; the other 146 get the fastest route.
- Time added, all trips: mean **+0.51 min** (95% CI +0.36 to +0.66), i.e. +3.1% of total fastest time. On the 54 changed trips: mean +1.9 min, median +1.7 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 902.8  (mean change **-3.62**, 95% CI -20.40 to +15.46; -0.4% overall).
  - On changed trips the safest had fewer held-out crashes on **37** and more on **17** (sign test p = 0.009).
  - Serious/fatal held-out crashes: 24.27 -> 23.91 per trip (-1.5%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -24.6% overall (mean change -548.7, 95% CI -873.9 to -294.5); on changed trips safer on **48**, worse on **6** (sign test p = 0.000).
- Model risk score (circular, reference only): -12.6%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -0.5% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 57 changed trips, +0.58 min and -0.4% held-out crashes (ours: +0.51 min, -0.4%).

### elderly  (200 trips)
- Safest differs from fastest on **59 trips (30%)**; the other 141 get the fastest route.
- Time added, all trips: mean **+0.55 min** (95% CI +0.40 to +0.71), i.e. +3.4% of total fastest time. On the 59 changed trips: mean +1.9 min, median +1.7 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 900.3  (mean change **-6.11**, 95% CI -23.26 to +13.79; -0.7% overall).
  - On changed trips the safest had fewer held-out crashes on **42** and more on **17** (sign test p = 0.002).
  - Serious/fatal held-out crashes: 24.27 -> 23.88 per trip (-1.6%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -24.5% overall (mean change -546.2, 95% CI -892.4 to -291.9); on changed trips safer on **52**, worse on **7** (sign test p = 0.000).
- Model risk score (circular, reference only): -13.0%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -0.8% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 64 changed trips, +0.65 min and -0.4% held-out crashes (ours: +0.55 min, -0.7%).

### sensitive_passenger  (200 trips)
- Safest differs from fastest on **56 trips (28%)**; the other 144 get the fastest route.
- Time added, all trips: mean **+0.51 min** (95% CI +0.36 to +0.67), i.e. +3.1% of total fastest time. On the 56 changed trips: mean +1.8 min, median +1.5 min.
- **Held-out crashes along the route** (2024+, severity-weighted): fastest 906.4 -> safest 905.9  (mean change **-0.56**, 95% CI -19.02 to +19.72; -0.1% overall).
  - On changed trips the safest had fewer held-out crashes on **39** and more on **17** (sign test p = 0.005).
  - Serious/fatal held-out crashes: 24.27 -> 23.98 per trip (-1.2%).
- **Realized per-vehicle risk** (held-out crashes per vehicle-mile along the route, TxDOT traffic counts): -23.1% overall (mean change -515.2, 95% CI -843.4 to -260.0); on changed trips safer on **49**, worse on **7** (sign test p = 0.000).
- Model risk score (circular, reference only): -10.9%.
- Baseline, a typical other route within the cap (155 trips with alternatives): -9.8% held-out crashes and +2.4 min vs the fastest. Our pick: -0.1% and +0.7 min on the same trips.
- Baseline, minimize model risk ignoring time: 59 changed trips, +0.55 min and +0.0% held-out crashes (ours: +0.51 min, -0.1%).

### Does the route-level model score predict later crashes? (independent check)
- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **-0.28** (95% CI -0.37 to -0.18, 150 trips with 3+ routes).
- Same check against realized per-vehicle risk: the lower model score also had the lower per-vehicle risk in **1013/1234 = 82%** of pairs (1 ties ignored).
- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in **474/1233 = 38%** of pairs (2 tied pairs ignored; 50% would be chance).

### Crashes per km (is the safest route just longer or shorter?)
- Held-out crashes per km along the route: fastest 64.36 -> safest 64.16 (route length 14.1 -> 14.1 km on average).

### By trip length (all profiles pooled)
- short: 210 cases, changed 26%, time +0.41 min, held-out crashes -2.5%
- medium: 240 cases, changed 31%, time +0.54 min, held-out crashes -0.9%
- long: 150 cases, changed 27%, time +0.64 min, held-out crashes +0.8%

Live TomTom times were available for 98% of trips (the rest use GraphHopper free-flow times). Held-out crashes: 32,182 (2024 to latest).
