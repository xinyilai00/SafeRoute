"""SafeRoute backend. Run: uvicorn app:app --reload --port 8000

GET /risk    the 200 m crash-risk grid (GeoJSON) for the heatmap toggle.
GET /health  liveness.

POST /route  fastest vs safest route (contract in ../CLAUDE.md). Set GH_URL to use GraphHopper;
             unset, it uses synthetic routes so the app is demoable. Header X-Data-Source says which.
"""
from pathlib import Path

import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import AliasChoices, BaseModel, Field

import routing
from scoring import hazards_avoided, score_route, to_latlon

RISK_PATH = Path(__file__).parent / "risk.geojson"


def _load_env():
    """Read KEY=VALUE lines from data/.env or the repo-root .env (both gitignored) into os.environ."""
    for p in (Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


_load_env()

_cache = {}
_filtered = {}  # serialized /risk?min_risk=X responses


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
        key = round(min_risk, 2)
        if key not in _filtered:
            gj = _load()
            feats = [f for f in gj["features"] if f["properties"]["risk"] >= key]
            _filtered[key] = json.dumps({**gj, "features": feats}, separators=(",", ":")).encode()
        return Response(_filtered[key], media_type="application/geo+json",
                        headers={"Cache-Control": "public, max-age=3600"})
    return FileResponse(RISK_PATH, media_type="application/geo+json",
                        headers={"Cache-Control": "public, max-age=3600"})


@app.get("/health")
def health():
    return {"ok": True}


# Per profile: how much slower the safest route may be, and the smallest risk drop worth a detour.
# If the best alternative saves less than min_gain of the fastest route's risk, we just return the
# fastest (fastest == safest) rather than make the driver lose minutes for nothing.
ROUTING_RULES = {
    "teen": {"max_detour": 1.25, "min_gain": 0.05},
    "elderly": {"max_detour": 1.35, "min_gain": 0.03},
    "sensitive_passenger": {"max_detour": 1.30, "min_gain": 0.03},
}
DEFAULT_RULES = {"max_detour": 1.25, "min_gain": 0.05}
KM_PER_MILE = 1.609344
# Event types allowed by the API contract; other hazards (roundabout, u_turn, crossing) still
# add to risk_score but aren't listed, so the app never sees an unknown type.
EVENT_TYPES = {"left_turn", "left_turn_major", "quick_exit_turn", "highway_merge", "high_crash_zone"}
MAX_CRASH_EVENTS = 5


class Point(BaseModel):
    lat: float
    lng: float = Field(validation_alias=AliasChoices("lng", "lon"))


# Pilot area; matches the crash grid. GraphHopper's map extract should cover at least this.
BOUNDS = {"lat": (29.95, 30.75), "lng": (-98.1, -97.3)}


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


def _pick_safest(cands, fastest, w, rules):
    """w=0 -> the fastest; w=1 -> lowest risk within the detour budget; between = blend.
    Falls back to the fastest when the winner doesn't beat it by rules["min_gain"]."""
    ok = [c for c in cands if c["minutes"] <= fastest["minutes"] * rules["max_detour"]]
    fs = fastest["score"] or 1.0
    best = min(ok, key=lambda c: (1 - w) * c["minutes"] / fastest["minutes"] + w * c["score"] / fs)
    if fastest["score"] > 0 and (fastest["score"] - best["score"]) / fastest["score"] < rules["min_gain"]:
        return fastest
    return best


@app.post("/route")
def route(req: RouteRequest):
    for name, p in (("origin", req.origin), ("destination", req.destination)):
        if not (BOUNDS["lat"][0] <= p.lat <= BOUNDS["lat"][1] and BOUNDS["lng"][0] <= p.lng <= BOUNDS["lng"][1]):
            raise HTTPException(422, f"{name} is outside the Austin pilot area")
    if abs(req.origin.lat - req.destination.lat) < 1e-4 and abs(req.origin.lng - req.destination.lng) < 1e-4:
        raise HTTPException(422, "origin and destination are the same place")
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
    safest = _pick_safest(cands, fastest, req.safety_weight,
                          ROUTING_RULES.get(req.profile, DEFAULT_RULES))
    f, s = fastest["score"], safest["score"]
    added = round(safest["minutes"] - fastest["minutes"], 1)
    avoided = hazards_avoided(fastest["hazards"], safest["hazards"])
    if safest is fastest:
        summary = "Fastest route is also the safest (alternatives are not meaningfully safer)"
    else:
        lead = f"+{round(added)} min" if round(added) > 0 else "Same time"
        turns = [a for a in avoided if "high-crash" not in a]
        zones = next((a for a in avoided if "high-crash" in a), None)
        parts = []
        if turns:
            parts.append(f"avoids {', '.join(turns)}")
        if zones:
            n = int(zones.split()[0])
            parts.append(f"passes {n} fewer high-crash zone{'s' if n != 1 else ''}")
        summary = f"{lead}, " + (" and ".join(parts) if parts else "lower crash exposure")
    body = {
        "fastest": _summary(fastest),
        "safest": _summary(safest),
        "comparison": {"minutes_added": added,
                       "risk_reduction_pct": round(100 * (f - s) / f) if f > 0 else 0,
                       "summary": summary},
    }
    return JSONResponse(body, headers={"X-Data-Source": provider.name})
