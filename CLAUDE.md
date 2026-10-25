# SafeRoute — CLAUDE.md (repo root)

24-hour HackTX hackathon project. Three people, three folders. This file holds what everyone needs: the product, the API contract, folder ownership, and git rules. Folder-specific rules live in each folder's own CLAUDE.md: `SafeRoute/CLAUDE.md` for the iOS app; `backend/` and `data/` keep their own.

## What the app is

An iOS navigation app that finds the **safest** driving route rather than the fastest, for new/teen drivers, elderly drivers, and drivers carrying sensitive passengers (pregnant, injured, infants). Google Maps minimizes time; we minimize expected risk subject to a detour budget. Pilot area is Austin, TX.

## How "safe" is defined (backend computes it; the app only displays it)

The backend asks a routing engine (GraphHopper) for several alternative routes, then scores each one against:
- historical crash density (Austin Vision Zero data, via `data/`'s `crash_risk(geometry)`)
- dangerous maneuvers (unprotected left turns, highway merges, roundabouts, U-turns)
- road characteristics (speed limit, lanes, lighting)
- for sensitive passengers, ride comfort (rough surface, sharp curves)

Each profile has different weights. The backend returns the fastest route and the safest route that is at most ~25% longer, plus a comparison.

Three profiles, exact wire strings: `"teen"`, `"elderly"`, `"sensitive_passenger"`.

## Team and folders

- **Nick:** iOS app in `SafeRoute/` and `SafeRoute.xcodeproj`. Only Nick commits Xcode changes.
- **Annikka:** `backend/` (FastAPI, GraphHopper calls, maneuver scoring, combining scores, ngrok). GraphHopper's jar, config, map file, and graph-cache stay outside the repo.
- **Xinyi:** `data/` (Austin crash data, risk grid, `crash_risk(geometry)` function called by the backend, GET /risk data, evaluation script comparing safest vs fastest on random trips).
- `backend/` and `data/` sit at the repo root, never inside `SafeRoute/`.
- Secrets (TomTom key, ngrok token) go in `.env`, never in code. **The repo is public.**

## API contract

**Do not change field names without telling the whole team.** Any change to the contract updates this section in the same commit.

The backend is served over ngrok; the URL changes whenever ngrok restarts, so post the current one in the team chat.

### POST /route

Request:
```json
{
  "origin": {"lat": 30.2849, "lng": -97.7341},
  "destination": {"lat": 30.2672, "lng": -97.7431},
  "profile": "teen",
  "safety_weight": 1.0,
  "avoid": ["tolls", "highways"]
}
```
- `profile`: `"teen"` | `"elderly"` | `"sensitive_passenger"`
- `safety_weight`: 0 = fastest, 1 = safest. Optional, default 1.0.
- `avoid`: optional list, any of `"tolls"` and `"highways"` (motorway and trunk roads, ramps included). Default `[]`: both are allowed, because they often save real time. It is a strong preference, not a ban: GraphHopper makes those roads about 100x less attractive, so a destination that is only reachable that way still gets a route. Unknown values are rejected with a 422. The response shape does not change; if the choice could not be honored, `comparison.summary` says so, e.g. `"(couldn't fully avoid tolls (12% of the route))"`.

Response:
```json
{
  "fastest": {
    "geometry": [[30.2849, -97.7341], [30.2841, -97.7338]],
    "eta_minutes": 11.4,
    "distance_km": 4.2,
    "risk_score": 14.0,
    "risk_events": [
      {"type": "left_turn_major", "lat": 30.2701, "lng": -97.7412, "description": "Left turn across Lamar Blvd"}
    ]
  },
  "safest": {"...": "same shape as fastest"},
  "comparison": {
    "minutes_added": 3.5,
    "risk_reduction_pct": 38,
    "summary": "+4 min, avoids 2 left turns across major roads"
  }
}
```
Rules:
- `geometry` is a list of `[lat, lng]` pairs. GraphHopper with `points_encoded=false` returns `[lng, lat]`, so the backend must flip each pair.
- `risk_score` is penalty points; lower is safer.
- `risk_events[].type` is one of: `left_turn`, `left_turn_major`, `quick_exit_turn`, `highway_merge`, `high_crash_zone`.
- If only one route is found, `fastest` and `safest` are identical and `minutes_added` is 0.

### GET /risk

GeoJSON FeatureCollection of polygons, each with `properties.risk` from 0 to 1. Coordinates follow standard GeoJSON order: `[lng, lat]`.

## Git rules

- Pull before you commit, build or test, then push. Keep commits small and self-contained, ideally one folder per commit.
- Stay in your own folder (see Team and folders). Tell the owner before touching someone else's folder. Only Nick commits Xcode changes.
- Never commit secrets. Keys and tokens live in `.env`, which is gitignored. Everything committed to this public repo is public forever.
- Generated and large artifacts stay out of the repo: GraphHopper jar, config, `.osm.pbf` map, `graph-cache/`, `data/raw/`, `DerivedData/`, `xcuserdata/` (see `.gitignore`).
- If a merge conflict touches any CLAUDE.md, stop and ask a human instead of resolving it automatically.
- Changing an API field name means telling the whole team and updating the contract above in the same commit.
