"""SafeRoute backend. Run: uvicorn app:app --reload --port 8000

GET /risk    the 200 m crash-risk grid (GeoJSON) for the heatmap toggle.
GET /health  liveness.

POST /route  fastest vs safest route (contract in ../CLAUDE.md). Set GH_URL to use GraphHopper;
             unset, it uses synthetic routes so the app is demoable. Header X-Data-Source says which.
"""
from pathlib import Path

import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import AliasChoices, BaseModel, Field

import routing
from scoring import hazards_avoided, score_route, to_latlon

RISK_PATH = Path(__file__).parent / "risk.geojson"

_cache = {}


def _load():
    if "gj" not in _cache:
        _cache["gj"] = json.loads(RISK_PATH.read_text())
    return _cache["gj"]


app = FastAPI(title="SafeRoute")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"])
app.add_middleware(GZipMiddleware, minimum_size=1024)  # 3.4 MB of JSON -> ~0.6 MB


@app.get("/risk")
def risk(min_risk: float = Query(0.0, ge=0, le=1)):
    """`?min_risk=0.3` drops quiet cells so the phone draws fewer polygons."""
    if not RISK_PATH.exists():
        raise HTTPException(503, "risk.geojson missing; run `python build_risk.py`")
    if min_risk > 0:
        gj = _load()
        feats = [f for f in gj["features"] if f["properties"]["risk"] >= min_risk]
        return JSONResponse({**gj, "features": feats}, media_type="application/geo+json")
    return FileResponse(RISK_PATH, media_type="application/geo+json",
                        headers={"Cache-Control": "public, max-age=3600"})


@app.get("/health")
def health():
    return {"ok": True}


MAX_DETOUR = 1.25  # safest route may be at most 25% slower than the fastest
KM_PER_MILE = 1.609344
# Event types allowed by the API contract; other hazards (roundabout, u_turn, crossing) still
# add to risk_score but aren't listed, so the app never sees an unknown type.
EVENT_TYPES = {"left_turn", "left_turn_major", "quick_exit_turn", "highway_merge", "high_crash_zone"}
MAX_CRASH_EVENTS = 5


class Point(BaseModel):
    lat: float
    lng: float = Field(validation_alias=AliasChoices("lng", "lon"))


class RouteRequest(BaseModel):
    origin: Point
    destination: Point
    profile: str = "teen"
    safety_weight: float = Field(1.0, ge=0, le=1)


def _events(hazards):
    crash = sorted((h for h in hazards if h["type"] == "high_crash_zone"),
                   key=lambda h: -h["points"])[:MAX_CRASH_EVENTS]
    rest = [h for h in hazards if h["type"] in EVENT_TYPES and h["type"] != "high_crash_zone"]
    return [{"type": h["type"], "lat": round(h["lat"], 6), "lng": round(h["lon"], 6),
             "description": h["description"]}
            for h in sorted(rest + crash, key=lambda h: h["distance_m"])]


def _summary(c):
    return {"geometry": to_latlon(c["coords"]), "eta_minutes": round(c["minutes"], 1),
            "distance_km": round(c["miles"] * KM_PER_MILE, 1),
            "risk_score": round(c["score"], 1), "risk_events": _events(c["hazards"])}


def _pick_safest(cands, fastest, w):
    """w=0 -> the fastest; w=1 -> lowest risk within the detour budget; between = blend."""
    ok = [c for c in cands if c["minutes"] <= fastest["minutes"] * MAX_DETOUR]
    fs = fastest["score"] or 1.0
    return min(ok, key=lambda c: (1 - w) * c["minutes"] / fastest["minutes"] + w * c["score"] / fs)


@app.post("/route")
def route(req: RouteRequest):
    provider = routing.get_provider()
    try:
        cands = provider.routes(req.origin.model_dump(), req.destination.model_dump())
    except Exception as e:  # GraphHopper down / bad point
        raise HTTPException(502, f"routing engine error: {e}")
    if not cands:
        raise HTTPException(404, "no route found")
    try:
        for c in cands:
            c["score"], c["hazards"] = score_route(c["coords"], req.profile, c["instructions"])
    except ValueError as e:
        raise HTTPException(422, str(e))

    fastest = min(cands, key=lambda c: c["minutes"])
    safest = _pick_safest(cands, fastest, req.safety_weight)
    f, s = fastest["score"], safest["score"]
    added = round(safest["minutes"] - fastest["minutes"], 1)
    avoided = hazards_avoided(fastest["hazards"], safest["hazards"])
    if safest is fastest:
        summary = "Fastest route is also the safest"
    else:
        summary = f"+{round(added)} min, " + (f"avoids {', '.join(avoided)}" if avoided
                                              else "lower crash exposure")
    body = {
        "fastest": _summary(fastest),
        "safest": _summary(safest),
        "comparison": {"minutes_added": added,
                       "risk_reduction_pct": round(100 * (f - s) / f) if f > 0 else 0,
                       "summary": summary},
    }
    return JSONResponse(body, headers={"X-Data-Source": provider.name})
