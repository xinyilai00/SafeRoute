# Grid model vs exposure model (200 trips x 3 profiles)

Both built from crashes through 2023. Judged per vehicle on 32,182 crashes from 2024-2025: each route's realized crash rate per vehicle-mile (TxDOT traffic counts) summed over its length; stretches with no TxDOT segment use the pooled realized rate of major collectors (102 per 100M vehicle-miles). Lower is safer.

| model | profile | reroutes | minutes added | realized per-vehicle risk vs fastest | 95% CI of mean change | changed trips safer / worse | crashes counted along route |
|---|---|---|---|---|---|---|---|
| grid | teen | 18% | +0.23 | **-7.9%** | -308.1 to -63.2 | 25 / 10 | -4.1% |
| grid | elderly | 22% | +0.37 | **-9.8%** | -369.6 to -91.0 | 31 / 14 | -4.8% |
| grid | sensitive_passenger | 20% | +0.28 | **-8.1%** | -313.8 to -66.5 | 26 / 13 | -3.8% |
| exposure | teen | 22% | +0.33 | **-20.3%** | -782.5 to -214.5 | 39 / 5 | -0.6% |
| exposure | elderly | 28% | +0.49 | **-23.4%** | -872.7 to -273.9 | 48 / 7 | -0.5% |
| exposure | sensitive_passenger | 26% | +0.44 | **-22.7%** | -856.9 to -254.8 | 45 / 8 | +0.4% |

Headroom (best realized per-vehicle route within each profile's detour cap, an upper bound nobody can pick in advance): elderly -26.4% for +0.68 min, sensitive_passenger -26.2% for +0.61 min, teen -23.7% for +0.51 min
