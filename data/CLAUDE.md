# data/ — CLAUDE.md

Owner: Xinyi. Read the root `CLAUDE.md` first (product, API contract, folder ownership, git rules); this file only adds what is specific to `data/`.

## What lives here

- `build_risk.py`: downloads the Austin Vision Zero crash CSV (Socrata `y2wy-tgr5`) into `raw/` (gitignored) and writes `risk.geojson`, a 200 m grid with `properties.risk` 0..1.
- `scoring.py`: `crash_risk(geometry, profile)` (what `backend/` calls) and `score_route(...)` (crash risk plus maneuver penalties).
- `app.py`, `routing.py`: a prototype `POST /route` + `GET /risk` on synthetic routes, a stopgap until Annikka's `backend/` has the real one. Delete or hand over once it does.
- Still to build: the evaluation script comparing safest vs fastest on ~200 random trips (needs real GraphHopper routes).

## Rules

- Stay in `data/`. Tell Annikka or Nick before touching `backend/` or `SafeRoute/`.
- Geometry order: GraphHopper and `crash_risk` take `[lng, lat]`; the API returns `[lat, lng]`; `risk.geojson` is `[lng, lat]`.
- `risk_events[].type` must stay within the contract's list; anything else only adds to `risk_score`.
- Don't commit `raw/`, `.venv/`, or any `.env`. `risk.geojson` is small enough to commit and is the only data artifact the team needs.
- Changing a contract field name means telling everyone and updating the root `CLAUDE.md` in the same commit.

## Keeping it current

`python refresh.py` (see README) downloads fresh data, rebuilds, and keeps the result only if the gate passes. `.github/workflows/data-refresh.yml` runs it weekly and opens a PR. Don't change the gate thresholds in `refresh.py` without telling the team.

## Run

```bash
cd data && .venv/bin/python -m pytest              # tests
.venv/bin/python build_risk.py [--refresh] [--since 2016]
.venv/bin/uvicorn app:app --port 8000              # prototype API; GH_URL=... for real GraphHopper
```
