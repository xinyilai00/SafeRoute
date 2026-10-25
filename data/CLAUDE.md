# data/ — CLAUDE.md

Owner: Xinyi. Read the root `CLAUDE.md` first (product, API contract, folder ownership, git rules); this file only adds what is specific to `data/`.

## What lives here

- **Data builders (write the data files, run offline):** `build_risk.py` (crash grid, `risk.geojson`), `calibrate_profiles.py` (teen/elderly crash-type ratios), `build_signals.py`, `build_pavement.py`, `analyze_weather.py`, `build_txdot.py` (compacts TxDOT's inventory; needs `raw/2025/`), `build_exposure.py` (per-segment crash rate per vehicle-mile), `calibrate_exposure.py` (one-off scale constant).
- **Runtime:** `app.py` (`POST /route`, `GET /risk`, `GET /health`), `routing.py` (GraphHopper candidates, closures, avoid options), `live.py` (TomTom live times and closures), `scoring.py` (`crash_risk(geometry, profile)` and `score_route(...)`; exposure model by default, `RISK_MODEL=grid` for the old one), `weather.py` (Open-Meteo heads-up), `llm.py` (guarded Gemini helper, not wired in).
- **Checks:** `backtest.py` (grid vs later crashes), `evaluate.py` (200-trip route evaluation, held-out crashes), `evaluate_exposure.py` (grid vs exposure model, per vehicle), `refresh.py` (self-updating pipeline and gate), `tests/`.
- `app.py` and `routing.py` are a working prototype of `POST /route` until Annikka's `backend/` replaces it.

## Rules

- Stay in `data/`. Tell Annikka or Nick before touching `backend/` or `SafeRoute/`.
- Geometry order: GraphHopper and `crash_risk` take `[lng, lat]`; the API returns `[lat, lng]`; `risk.geojson` is `[lng, lat]`.
- `risk_events[].type` must stay within the contract's list; anything else only adds to `risk_score`.
- Don't commit `raw/`, `.venv/`, or any `.env`. `risk.geojson` is small enough to commit and is the only data artifact the team needs.
- Changing a contract field name means telling everyone and updating the root `CLAUDE.md` in the same commit.

## Keeping it current

`python refresh.py` (see README) downloads fresh data, rebuilds (including the per-vehicle segment rates), and keeps the result only if the gate passes. `.github/workflows/data-refresh.yml` runs it weekly and opens a PR. Don't change the gate thresholds in `refresh.py` without telling the team.

## Run

```bash
cd data && .venv/bin/python -m pytest              # tests
.venv/bin/python build_risk.py [--refresh] [--since 2016]
.venv/bin/uvicorn app:app --port 8000              # prototype API; GH_URL=... for real GraphHopper
```
