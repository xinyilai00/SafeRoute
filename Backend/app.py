"""SafeRoute backend. Run: uvicorn app:app --reload --port 8000

GET /risk    the 200 m crash-risk grid (GeoJSON) for the heatmap toggle.
GET /health  liveness.

Teammate B: add /route here (or `from scoring import score_route` elsewhere) and call
    score_route(route["points"], profile, route["instructions"])
for each GraphHopper candidate.
"""
from pathlib import Path

import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

RISK_PATH = Path(__file__).parent / "data" / "risk.geojson"

_cache = {}


def _load():
    if "gj" not in _cache:
        _cache["gj"] = json.loads(RISK_PATH.read_text())
    return _cache["gj"]


app = FastAPI(title="SafeRoute")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
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
