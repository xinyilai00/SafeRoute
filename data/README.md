# data/ — crash data, risk grid, crash_risk()

```bash
cd data
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build_risk.py          # downloads crashes CSV into raw/ (gitignored), writes risk.geojson
.venv/bin/python -m pytest
```

## What backend/ calls

```python
from scoring import crash_risk
points, events = crash_risk(geometry, profile)   # geometry: [[lng, lat], ...] (GraphHopper order), NOT [lat, lng]
# events: [{type: "high_crash_zone", lat, lon, distance_m, points, description}]
```

`risk.geojson` is the `GET /risk` payload: polygons with `properties.risk` in 0..1, `[lng, lat]` coordinates.

## Prototype backend (stopgap for Annikka's `backend/`)

`app.py`, `routing.py` and the maneuver half of `scoring.py` (`score_route`) are a working
`POST /route` written against the contract in the root CLAUDE.md. It runs on synthetic routes until
GraphHopper is wired in, so Nick can demo the app. Annikka: lift or replace any of it; delete when
`backend/` has the real one.

```bash
.venv/bin/uvicorn app:app --port 8000                                          # fake routes (X-Data-Source: fake)
GH_URL=http://localhost:8989 GH_PROFILE=car .venv/bin/uvicorn app:app --port 8000   # real GraphHopper
ngrok http 8000
```

- Safest = best blend of ETA and risk among candidates at most 25% slower; `safety_weight` 0 = fastest, 1 = safest.
- GraphHopper needs LM or flexible mode (`alternative_route` doesn't work with CH).
- `risk_events` only uses the contract's types; roundabouts, U-turns and fast-road crossings count toward
  `risk_score` but aren't listed.
- Unknown profile -> 422; engine down -> 502.
- `score_route(coords, profile, instructions)` takes GraphHopper's `route["points"]["coordinates"]` and `route["instructions"]`.
  Per-profile weights are in `PROFILES` in `scoring.py` (profiles differ only by measured values; see above).

## Live traffic (TomTom, optional)

Set `TOMTOM_API_KEY` in the gitignored `.env`; without it everything below is skipped and `/route` uses GraphHopper's free-flow times. `live.py` does three things per `/route`:
- **Closures:** current "road closed" incidents for the Austin box (cached 2 min) are sent to GraphHopper as a blocked area (custom model, priority 0), so it routes around closed streets. If an endpoint sits inside a closure it retries without blocking.
- **Live ETAs:** each candidate is timed with TomTom Calculate Route (`traffic=true`, the candidate's own points as `supportingPoints`), in parallel, replacing GraphHopper's minutes. All live or none, never a mix. GraphHopper's free-flow times were often far too optimistic for non-highway routes (23 vs 33 min).
- **Sanity checks:** candidates that still touch a closure, or whose live time is over 2.5x free-flow and 8+ min more, are dropped (unless that would drop all of them). If the chosen route still crosses a closure, the summary says so.
- Response headers: `X-Live-Traffic: tomtom|off`, `X-Closures-Skipped: N`. Free tier is about 2,500 requests/day; one `/route` costs one TomTom call per candidate (up to 4) plus a cached incidents call.

## Avoid tolls / highways

`POST /route` accepts an optional `avoid` list (`"tolls"`, `"highways"`; contract in the root `CLAUDE.md`). `routing.build_custom_model` turns it into one GraphHopper custom model together with the closure block, so the two never overwrite each other: `toll == ALL` and `road_class == MOTORWAY || road_class == TRUNK` get priority x0.01 (soft), closed streets priority 0.
- `toll` is only requested as a path detail when `tolls` is in `avoid`, so a GraphHopper import without the toll value can't break ordinary requests.
- If GraphHopper answers 400 to the custom model, `/route` retries without the closure block (keeping `avoid`), then without `avoid`, and says so in the summary. Other errors (engine down, timeout) are not retried.
- After routing, the chosen routes are checked: if more than 5% of a route is still on an avoided road type, the summary says "couldn't fully avoid ...".
- Header `X-Avoid-Applied` lists what was actually applied (`none` if nothing). Fake routes ignore `avoid`.
- On real Austin trips, avoiding highways costs a lot of time (Round Rock to UT: 22.8 to 37.7 min live); avoiding tolls costs little (36.9 to 38.9 min Cedar Park to the airport).

## Self-updating pipeline (`refresh.py`)

One command keeps the data current and refuses to ship a worse model:

```bash
cd data && .venv/bin/python refresh.py             # download, rebuild, check, keep or roll back
.venv/bin/python refresh.py --dry-run              # everything, then restore the old files (writes nothing)
.venv/bin/python refresh.py --skip-download        # rebuild from the files already in raw/
```

1. **Download and rebuild** (all public, keyless sources): new crashes and victim records, signals, pavement, and the profile ratios and risk grid. The weather effect is only recomputed when a new calendar year has completed.
2. **Forward check:** crashes that arrived since the last build are genuinely new to the old grid. The share landing in the old grid's top 10% of squares is logged to `history.json` (chance is 10%). On a real test, a grid built months earlier put 59-60% of the later crashes in its top 10%, steady across 3, 6 and 12 months. It only warns (a change in the world isn't a reason to reject a rebuild).
3. **Gate** (fixed numeric thresholds at the top of `refresh.py`, never a language model). The rebuild is accepted only if: the grid is structurally sound and a similar size, it correlates >= 0.95 with the previous grid, a rolling backtest (train through two years ago) captures >= 50% and hasn't dropped more than 3 points, the 200-trip route evaluation re-scored offline from `eval/trips.json.gz` (no GraphHopper or TomTom needed) still shows the safest route cutting realized per-vehicle crash risk by >= 8% (about -20% now; the old grid model is held to crashes counted along the route, >= 2%) with route-score agreement >= 55% (82% now), and the unit tests pass. The segment rates are rebuilt on every run (`build_exposure.py`); the TxDOT segment file is not (TxDOT publishes once a year).
4. **Accepted:** new files stay, `history.json` and `eval/REFRESH_REPORT.md` are updated. **Rejected:** every file is restored and the reasons are logged.

`.github/workflows/data-refresh.yml` runs this every Monday (and on demand from the Actions tab) and opens a pull request with the report; a person merges it. One-time setup: Settings > Actions > General > tick "Allow GitHub Actions to create and approve pull requests". Scheduled runs only fire once the workflow file is on `main`.

`risk.geojson` now carries a `meta` member (data cutoff, build time, crash count) so CI can tell which crashes are new without the old download. This keeps the data current and catches drift; it cannot guarantee better routes, since new crash data arrives gradually.

## Profiles, signals and bridges (measured where possible)

- **Teen and elderly are different because of data, not hand-set weights.** `calibrate_profiles.py` compares collision types in crashes with a teen driver (15-19, 422 crashes) or a driver 65+ (520 crashes) against all serious/fatal crashes, shrinks the ratios toward 1, and writes `profile_ratios.json`. `build_risk.py` uses them to build `risk_teen` and `risk_elderly` grid layers (per-type crash weights times those ratios), and `scoring.py` uses the matching layer. Findings: teens are over-represented in opposite-direction (x1.42 raw) and single-vehicle crashes and at night (x1.28), but not in left-turn crashes (x0.95); drivers 65+ in angle (x1.44) and left-turn (x1.14) crashes, and almost never at night (x0.44).
- **Limits.** The victim table (xecs-rpy9) only covers serious and fatal crashes, so a per-square age grid would be mostly noise; only the global type ratios are used. The backtest (`python backtest.py`) shows the profile grids are no worse than the general one and no clearly better: teen 49.2% vs 49.2% of held-out crashes captured in the top 10% of squares, elderly 42.0% vs 40.7% (n = 61 and 81, so within noise). Night driving is a real measured difference but needs a departure time in the request, which isn't in the contract yet.
- **Everything else is the car baseline** except `left_crash` (scaled by the measured left-turn ratio) and the sensitive-passenger curvature penalty, which has no data behind it (an assumption). The earlier hand-set teen/elderly maneuver weights were removed because nothing measured supports them.
- **Signals.** `build_signals.py` writes `signals.json` (1,105 active traffic signals from Austin's signal table; pedestrian beacons excluded). A left turn within 35 m of a signal is "signalized"; a left on a fast road with no signal nearby is the "unprotected" case. A signal does not guarantee a protected arrow; the data doesn't say.
- **Bridges and tunnels.** GraphHopper's `road_environment` detail marks them; crash risk there is scaled by 0.5 because the grid square under an overpass is mostly the road below. Where a stretch is also a highway the smaller factor wins. An assumption, not measured.

## Open data pulled and what came of it

- **Street condition (used).** `build_pavement.py` downloads the City of Austin's street condition layer (28k segments with the city's own A-F grades) to `street_condition.json` (2.1 MB). For the sensitive-passenger profile, stretches graded F count fully and D half as "rough"; the penalty is 6 points per rough km (`rough` in `PROFILES`). WHERE the pavement is rough is real data; the 6 points/km is an assumption. TxDOT-maintained roads (highways) aren't covered, so they have no pavement data.
- **Weather (measured, shown as a heads-up only).** `analyze_weather.py` joins 172,805 crashes (2014-2025) to hourly NOAA observations from Austin-Bergstrom (GHCNh) and compares each condition with dry hours at the same local hour-of-day and weekday/weekend (`weather_effect.json`). Rain hours have 1.43x the crashes of dry hours (95% range 1.41-1.45, 15,760 crashes), low visibility 1.33x, freezing 0.89x. By type: single-vehicle 2.17x, opposite-direction 2.37x, intersection types about 1.2x. Serious/fatal crashes did NOT rise in rain (1.00, range 0.90-1.10). This is per hour, not per vehicle-mile; rain lowers traffic, so the per-vehicle effect is likely larger. It is deliberately NOT in the risk grid: a rain-weighted grid correlates 0.995 with the normal one, so it would not change which route wins. `weather.py` reads current conditions from Open-Meteo (cached 10 min, no key), and `/route` adds headers `X-Weather` (rain / dry / unknown) and, while raining, `X-Weather-Crash-Ratio` (1.43) for the app to show a heads-up.
- **Traffic counts.** Austin's own camera and radar counts cover only 21-53 intersections a year with no coordinates, so they can't give citywide exposure. TxDOT's 2025 Roadway Inventory can, and is used by the exposure model (above).
- **NHTSA FARS cross-check.** Among drivers in fatal crashes, 2019-2023: drivers 65+ crash in the dark far less than others (dark share ratio 0.55 nationally, 0.59 in Texas) and teens slightly more (1.13 nationally, 1.09 Texas). That agrees in direction with the Austin ratios (65+ night 0.44, teen night 1.28; magnitudes differ). Exposure differs by age (older drivers drive less at night), so this is a share, not a risk rate.

## Where to get more data

- **Traffic volumes (exposure):** TxDOT Roadway Inventory, annual ZIPs at https://www.txdot.gov/data-maps/roadway-inventory.html (2025: https://www.txdot.gov/content/dam/docs/division/tpp/roadway-inventory/2025.zip), and TxDOT traffic count maps at https://www.txdot.gov/data-maps/traffic-count-maps.html. Contents of the ZIP not yet checked; TxDOT says its GIS data may not be used commercially.
- **Weather (more):** National Weather Service API, no key: https://www.weather.gov/documentation/services-web-api (active alerts: `https://api.weather.gov/alerts/active?point=30.27,-97.74`). Open-Meteo, free, no key for light use: https://open-meteo.com/en/docs. TomTom incidents (already used for closures) also include weather categories (fog, rain, ice, wind, flooding).
- **Historical weather and lighting per crash:** TxDOT CRIS, https://www.txdot.gov/data-maps/crash-reports-records/crash-data-analysis-statistics.html (CRIS Query tool, or the Crash Data Request form for bulk).

## Exposure model: crash rate per vehicle-mile (default)

The grid counts crashes per 200 m square, and busy roads simply have more crashes. What a driver cares about is risk per trip. TxDOT's 2025 Roadway Inventory (`raw/2025/`, not in git: 3 GB) gives every highway, arterial and collector a real traffic count, so `build_exposure.py` computes each segment's severity-weighted crash rate per 100 million vehicle-miles.

- **Files:** `build_txdot.py` compacts the inventory to `txdot_segments.json` (16,245 segments, road classes 1-6; class 7 local streets are dropped because about half carry a placeholder count of 281 vehicles a day). `build_exposure.py` matches crashes to segments (nearest within 15 m), smooths short segments toward their road class (empirical Bayes), and writes `segment_rates.json` (general, teen and elderly variants). `calibrate_exposure.py` sets `EXPOSURE_POINTS_PER_RATE` so an average minor arterial/collector scores the same under both models.
- **What it found** (69,000 crashes 2019-2023 matched to segments): severity-weighted crashes per 100M vehicle-miles are about 17 on the interstate, 12 on other freeways, 22 on principal arterials, 100-115 on minor arterials and major collectors. Per vehicle-mile, freeways are roughly 4-9 times safer than ordinary arterials (0.25-0.33x; 0.20-0.28x for serious and fatal crashes), and the ordering holds under two different ways of matching crashes to roads. The grid model's flat 0.6 highway factor hid this.
- **Smoothing is chosen by evidence:** trained on crashes through 2023, segment-level rates predicted 2024-2025 crash counts far better than class averages (held-out log-likelihood +17,600), and a small amount of smoothing (M = 0.005 per 100M vehicle-miles) beat raw rates (+8,150). `python build_exposure.py --validate` reproduces it.
- **Head-to-head on the 200 cached trips** (`python evaluate_exposure.py`, report in `eval/EXPOSURE_COMPARISON.md`; both models built from crashes through 2023, judged per vehicle on 2024-2025 crashes): realized per-vehicle risk of the chosen route vs the fastest, grid model -8% to -10%, exposure model -20% to -23% (safer on 39/5, 48/7 and 45/8 changed trips), for +0.3 to +0.5 minutes. That is about 87% of the best possible per-vehicle improvement. The route score agrees with the realized per-vehicle risk in 82% of route pairs (grid model: 63%).
- **What it no longer does:** reduce the raw count of crashes along the route (about 0%, vs -4% for the grid). That count rewards avoiding busy roads whether or not they're riskier per car.
- **Limits:** exposure uses TxDOT's 2025 volume for every crash year; local streets (no real counts) fall back to the grid, and the realized-risk check gives unmatched stretches the pooled rate of major collectors; two-way counts are used for both directions; crash locations are matched, not verified. The heatmap (`GET /risk`) still shows crash density per square, not per-vehicle risk.
- **Switch:** `RISK_MODEL=grid` (environment) restores the old crash-count model; it is also what the older unit tests use. If the TxDOT files are missing the backend falls back to the grid automatically.
- **Annual refresh:** download the new inventory into `raw/2025/` (rename for the year) and run `python build_txdot.py`, `python build_exposure.py --validate`, then `python calibrate_exposure.py` and update the constant. The weekly workflow rebuilds only the crash-dependent rates.

## Method notes

- Severity weights (build_risk.py): fatal 10, serious 6, non-incapacitating 2, possible 1, no injury 0.5. Cell value is log-scaled, then divided by the max, so the heatmap isn't one red dot. `--weights cost` uses the city's per-crash cost estimates instead; `backtest.py` shows it predicts later crashes slightly worse (rare fatals add noise), so severity is the default.
- Left-turn layer: crashes whose `collsn_desc` involves a left turn get their own grid value, `left_risk`. A left turn's penalty grows with `left_risk` at the turn's cell, and a left in a hot cell (>= 0.55) is reported as `left_turn_major`. In the backtest this layer predicts later left-turn crashes only marginally better than overall risk (39% vs 36% captured in the top 5% of cells).
- Backtest (`python backtest.py`, train <= 2023, test 2024+): the top 10% of grid cells by risk captured about 58% of later crashes, vs ~10% by chance. (This tests the crash-count grid, which the heatmap still shows; the exposure model's own held-out tests are in the section above.)
- Routing rules (`ROUTING_RULES` in `app.py`): per-profile detour cap (teen 20%, elderly 30%, sensitive 25%) and a minimum risk gain (3-5%). If no alternative clears it, `/route` returns the fastest as the safest.
- Recency: `build_risk.py` discounts older crashes with a 5-year half-life (`--halflife 0` to turn off). In the backtest this helped slightly; 3x3 spatial smoothing hurt, so it is not used.
- Ride comfort (`sensitive_passenger` only; no data behind the weights): smooth curving along the route (heading change over 25 m steps, ignoring corners) at 0.03 points/degree, and rough pavement (city grade F counts fully, D half) at 6 points/km. They add to `risk_score` only; they are not contract event types. The `elderly` profile has no curvature penalty.
- `/route` rejects points outside the Austin pilot box (422) and identical origin/destination (422). `GET /risk?min_risk=` responses are cached in memory. `GH_URL` / `GH_PROFILE` can live in a gitignored `.env` (repo root or `data/`).
- Highways and bridges (grid model, and the fallback under the exposure model): raw crash counts over-penalise highways (they carry far more traffic), so stretches GraphHopper labels motorway/trunk have their grid crash risk scaled by `HIGHWAY_CRASH_FACTOR` (0.6, a judgment call), and bridges/tunnels by 0.5. Under the exposure model (default) a stretch that matches a TxDOT segment is scored from that segment's measured per-vehicle rate instead, so these two factors only touch stretches with no TxDOT match (mostly local streets).
- Route choice (`_pick_safest` in `app.py`): candidates within the profile's detour cap are ranked by `time/fastest_time + safety_weight * beta * risk/fastest_risk`, so a detour must cut risk by more than it costs in time (beta 1 = even trade; elderly and sensitive passengers use 1.5). Highways and other faster roads are kept whenever the time they save outweighs their risk. On 10 real Austin trips the safest route then differs from the fastest only occasionally, because routes that avoid highways cost 15-30% more time for 15-22% less risk. Raise `beta` in `ROUTING_RULES` to favour safety more.
- Crash risk (grid model) = grid value sampled every 20 m, length-weighted. Under the exposure model the same 20 m samples take their TxDOT segment's rate per vehicle-mile when one matches within 15 m (and GraphHopper agrees it isn't a frontage road beside a freeway), and the grid value otherwise.
- "Unprotected left across a major road" approximation: a left on a fast road (cell's median crash speed limit >= 40 mph, or a highway-like street name) with no traffic signal within 35 m (`signals.json`) adds the `left_major` penalty. A signal doesn't guarantee a protected arrow; the data doesn't say. TxDOT's `SPD_MAX` was not used: for city streets it often shows the statutory maximum, not the posted limit.
- Quick turn after an exit: a maneuver within 300 m of a ramp/exit instruction. Exit detection reads the instruction `text` for "exit"/"ramp"; check against real GraphHopper output.
