"""SafeRoute backend. Run: uvicorn app:app --reload --port 8000

GET /risk    the 200 m crash-risk grid (GeoJSON) for the heatmap toggle.
GET /health  liveness.

POST /route  fastest vs safest route (contract in ../CLAUDE.md). Set GH_URL to use GraphHopper;
             unset, it uses synthetic routes so the app is demoable. Header X-Data-Source says which.
"""
from pathlib import Path

import json
import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import AliasChoices, BaseModel, Field, field_validator

import live
import weather
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


# Per profile:
#   max_detour: hard cap on how much slower the safest route may be.
#   min_gain:   smallest risk drop worth a detour; below it the fastest is returned.
#   beta:       how many percent of time a percent of risk is worth at safety_weight=1. Routes are
#               ranked by cost = time/fastest_time + safety_weight * beta * risk/fastest_risk, so a
#               detour must cut risk by more than it adds time (scaled by beta). beta 1 is an even
#               trade; higher means the profile pays more time for safety.
ROUTING_RULES = {
    "teen": {"max_detour": 1.30, "min_gain": 0.05, "beta": 1.5},
    "elderly": {"max_detour": 1.30, "min_gain": 0.03, "beta": 1.5},
    "sensitive_passenger": {"max_detour": 1.30, "min_gain": 0.03, "beta": 1.5},
}
# Chosen on the development era (models built through 2021, judged on 2022-23), where per-vehicle risk reduction is flat
# at about -20% to -23% for any cap from 1.20 up and extra minutes buy almost nothing beyond ~1.30 / beta 1.5.
# Teen used a tighter cap (1.20) before, for no data-based reason; 1.30 gains ~2.6 points for ~0.14 min there.
DEFAULT_RULES = {"max_detour": 1.30, "min_gain": 0.05, "beta": 1.5}
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
    avoid: list[Literal["tolls", "highways"]] = Field(default_factory=list)  # optional road types to steer clear of

    @field_validator("avoid")
    @classmethod
    def _unique(cls, v):
        return [a for a in routing.AVOID_OPTIONS if a in v]  # dedupe, canonical order


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
    """Rank candidates within the detour cap by time + w*beta*risk (both relative to the fastest),
    so highways and other faster roads are kept whenever the time they save outweighs their risk.
    w=0 is the fastest. Falls back to the fastest when the winner saves < rules["min_gain"] risk."""
    ok = [c for c in cands if c["minutes"] <= fastest["minutes"] * rules["max_detour"]]
    fs = fastest["score"] or 1.0
    best = min(ok, key=lambda c: c["minutes"] / fastest["minutes"]
               + w * rules["beta"] * c["score"] / fs)
    if fastest["score"] > 0 and (fastest["score"] - best["score"]) / fastest["score"] < rules["min_gain"]:
        return fastest
    return best


AVOID_NOTE_SHARE = 0.05  # if more than 5% of a route is still on an avoided road type, say so


def _fetch_candidates(provider, o, d, blocked, avoid):
    """Candidates from the routing engine, plus the avoid options actually applied.

    GraphHopper answers 400 for a custom model it can't use (an endpoint inside a closure, a missing
    toll value). Only then do we retry, dropping the closure block first (keeping the user's avoid),
    then the avoid itself. Any other error (engine down, timeout) is raised straight away.
    """
    attempts = [(blocked, avoid), (None, avoid), (blocked, []), (None, [])]
    seen, last = set(), None
    for blk, av in attempts:
        key = (bool(blk), tuple(av))
        if key in seen:
            continue
        seen.add(key)
        try:
            return provider.routes(o, d, blocked=blk, avoid=av), list(av)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 400:
                raise
            last = e
    raise last


def _avoid_note(cands, requested, applied, provider_name):
    """Honest one-liner when the user's avoid choice wasn't (fully) honoured, else ""."""
    if not requested or provider_name == "fake":
        return ""
    missed = [a for a in requested if a not in applied]
    if missed:
        return f" (couldn't avoid {' or '.join(missed)}: the routing engine rejected it)"
    notes = []
    for a, key, kinds in (("tolls", "tolls", ["all"]), ("highways", "road_classes", routing.HIGHWAY_CLASSES)):
        if a in requested:
            share = max(routing.share_on(c["coords"], c.get(key), kinds) for c in cands)
            if share > AVOID_NOTE_SHARE:
                notes.append(f"{a} ({share:.0%} of the route)")
    return f" (couldn't fully avoid {' or '.join(notes)})" if notes else ""



def _weather_headers():
    """Heads-up headers (not part of the contract's body): X-Weather = rain | dry | unknown; while it
    is raining X-Weather-Crash-Ratio is the measured crashes-per-hour ratio vs a dry hour (about 1.4)."""
    wx = weather.current()
    if wx is None:
        return {"X-Weather": "unknown"}
    state = "rain" if wx["raining"] else "dry"
    headers = {"X-Weather": state}
    if wx["raining"] and (ratio := weather.rain_crash_ratio()):
        headers["X-Weather-Crash-Ratio"] = f"{ratio:.2f}"
    return headers


@app.post("/route")
def route(req: RouteRequest):
    for name, p in (("origin", req.origin), ("destination", req.destination)):
        if not (BOUNDS["lat"][0] <= p.lat <= BOUNDS["lat"][1] and BOUNDS["lng"][0] <= p.lng <= BOUNDS["lng"][1]):
            raise HTTPException(422, f"{name} is outside the Austin pilot area")
    if abs(req.origin.lat - req.destination.lat) < 1e-4 and abs(req.origin.lng - req.destination.lng) < 1e-4:
        raise HTTPException(422, "origin and destination are the same place")
    provider = routing.get_provider()
    o, d = req.origin.model_dump(), req.destination.model_dump()
    blocked = live.closure_area() if live.enabled() and provider.name != "fake" else None
    try:
        cands, applied = _fetch_candidates(provider, o, d, blocked, req.avoid)
    except Exception as e:  # GraphHopper down / bad point
        raise HTTPException(502, f"routing engine error: {e}")
    if not cands:
        raise HTTPException(404, "no route found")
    # live traffic ETAs + closure filtering (no-op without TOMTOM_API_KEY, and skipped for fake routes)
    info = live.apply_live(cands) if provider.name != "fake" else {"live": False, "dropped": 0}
    try:
        for c in cands:
            c["score"], c["hazards"] = score_route(c["coords"], req.profile, c["instructions"],
                                                   road_classes=c.get("road_classes"),
                                                   road_environment=c.get("environments"))
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
    if live.enabled() and provider.name != "fake" and live.hits_closure(safest["coords"]):
        summary += " (warning: this route crosses a reported road closure)"
    elif info["dropped"]:
        summary += f" (avoids {info['dropped']} route{'s' if info['dropped'] != 1 else ''} through road closures)"
    summary += _avoid_note([fastest, safest], req.avoid, applied, provider.name)
    body = {
        "fastest": _summary(fastest),
        "safest": _summary(safest),
        "comparison": {"minutes_added": added,
                       "risk_reduction_pct": round(100 * (f - s) / f) if f > 0 else 0,
                       "summary": summary},
    }
    return JSONResponse(body, headers={"X-Data-Source": provider.name,
                                       "X-Live-Traffic": "tomtom" if info["live"] else "off",
                                       "X-Closures-Skipped": str(info["dropped"]),
                                       "X-Avoid-Applied": ",".join(applied) or "none",
                                       **_weather_headers()})
