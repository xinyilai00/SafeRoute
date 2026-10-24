# SafeRoute backend

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build_risk.py          # downloads crashes CSV, writes data/risk.geojson
.venv/bin/uvicorn app:app --port 8000   # GET /risk, GET /health
.venv/bin/python -m pytest
```

## For teammate B (/route)

```python
from scoring import score_route
risk, hazards = score_route(route["points"], "car", route["instructions"])  # "car" | "bike" | "foot"
final = eta_minutes + w * risk   # w from the fastest<->safest slider
```

- `route["points"]`: encoded polyline string (precision 5) or GeoJSON `[lon, lat]` list/LineString. Request `instructions=true`.
- `hazards`: `[{type, lat, lon, distance_m, points, description}]`, ready to pin on the map.
- Hazard types: `crash_zone`, `left_turn`, `left_turn_major`, `merge`, `roundabout`, `u_turn`, `quick_after_exit`, `crossing` (foot).
- Weights live in `PROFILES` in `scoring.py`.

## Method notes

- Severity weights (build_risk.py): fatal 10, serious 6, non-incapacitating 2, possible 1, no injury 0.5. Cell value is log-scaled then divided by the max, so the heatmap isn't one red dot.
- Crash risk = grid value sampled every 20 m, length-weighted (a 200 m run through a risk-1.0 cell adds `crash` points).
- "Unprotected left across a major road" approximation: a left where the grid cell's median crash speed limit is >= 40 mph, or the street name looks like a highway/arterial. Signal presence isn't known.
- Quick turn after an exit: a maneuver within 300 m of a ramp/exit instruction, scaled by how short the gap is.
- Exit/ramp detection reads GraphHopper's instruction `text`, so it depends on that text containing "exit" or "ramp"; check against real responses.
