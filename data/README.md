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

## Method notes

- Severity weights (build_risk.py): fatal 10, serious 6, non-incapacitating 2, possible 1, no injury 0.5. Cell value is log-scaled, then divided by the max, so the heatmap isn't one red dot.
- Crash risk = grid value sampled every 20 m, length-weighted.
- "Unprotected left across a major road" approximation: a left where the cell's median crash speed limit is >= 40 mph, or the street name looks like a highway/arterial. Signal presence isn't known.
- Quick turn after an exit: a maneuver within 300 m of a ramp/exit instruction. Exit detection reads the instruction `text` for "exit"/"ramp"; check against real GraphHopper output.
