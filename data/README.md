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
  Per-profile weights are in `PROFILES` in `scoring.py`.

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

## Method notes

- Severity weights (build_risk.py): fatal 10, serious 6, non-incapacitating 2, possible 1, no injury 0.5. Cell value is log-scaled, then divided by the max, so the heatmap isn't one red dot. `--weights cost` uses the city's per-crash cost estimates instead; `backtest.py` shows it predicts later crashes slightly worse (rare fatals add noise), so severity is the default.
- Left-turn layer: crashes whose `collsn_desc` involves a left turn get their own grid value, `left_risk`. A left turn's penalty grows with `left_risk` at the turn's cell, and a left in a hot cell (>= 0.65) or on a fast road is reported as `left_turn_major`. In the backtest this layer predicts later left-turn crashes only marginally better than overall risk (39% vs 36% captured in the top 5% of cells).
- Backtest (`python backtest.py`, train <= 2023, test 2024+): the top 10% of cells by risk captured about 56% of later crashes, vs ~10% by chance.
- Routing rules (`ROUTING_RULES` in `app.py`): per-profile detour cap (teen 20%, elderly 30%, sensitive 25%) and a minimum risk gain (3-5%). If no alternative clears it, `/route` returns the fastest as the safest.
- Recency: `build_risk.py` discounts older crashes with a 5-year half-life (`--halflife 0` to turn off). In the backtest this helped slightly; 3x3 spatial smoothing hurt, so it is not used.
- Ride comfort: smooth curving along the route (heading change over 25 m steps, ignoring corners) is penalised for `sensitive_passenger` (0.03/degree) and a little for `elderly` (0.01/degree). It adds to `risk_score` only; it is not a contract event type.
- `/route` rejects points outside the Austin pilot box (422) and identical origin/destination (422). `GET /risk?min_risk=` responses are cached in memory. `GH_URL` / `GH_PROFILE` can live in a gitignored `.env` (repo root or `data/`).
- Highways: raw crash counts over-penalise highways (they carry far more traffic), so stretches GraphHopper labels motorway/trunk (`details=road_class`) have their grid crash risk scaled by `HIGHWAY_CRASH_FACTOR` (0.6, a judgment call; merges and exits are still penalised separately).
- Route choice (`_pick_safest` in `app.py`): candidates within the profile's detour cap are ranked by `time/fastest_time + safety_weight * beta * risk/fastest_risk`, so a detour must cut risk by more than it costs in time (beta 1 = even trade; elderly and sensitive passengers use 1.5). Highways and other faster roads are kept whenever the time they save outweighs their risk. On 10 real Austin trips the safest route then differs from the fastest only occasionally, because routes that avoid highways cost 15-30% more time for 15-22% less risk. Raise `beta` in `ROUTING_RULES` to favour safety more.
- Crash risk = grid value sampled every 20 m, length-weighted.
- "Unprotected left across a major road" approximation: a left where the cell's median crash speed limit is >= 40 mph, or the street name looks like a highway/arterial. Signal presence isn't known.
- Quick turn after an exit: a maneuver within 300 m of a ramp/exit instruction. Exit detection reads the instruction `text` for "exit"/"ramp"; check against real GraphHopper output.
