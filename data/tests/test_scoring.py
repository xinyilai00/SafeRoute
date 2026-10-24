import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import scoring  # noqa: E402
from app import app  # noqa: E402

# Straight line through downtown Austin and one through empty ranch land.
DOWNTOWN = [[-97.7431, 30.2672], [-97.7431, 30.2850]]
EMPTY = [[-98.05, 30.70], [-98.05, 30.72]]


def test_downtown_riskier_than_empty():
    assert scoring.score_route(DOWNTOWN, "car")[0] > scoring.score_route(EMPTY, "car")[0] == 0


def test_encoded_polyline_matches_coordinates():
    # classic Google doc example: (38.5,-120.2) (40.7,-120.95) (43.252,-126.453)
    assert scoring.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")[0] == (-120.2, 38.5)


def test_left_turn_penalised_more_on_bike_than_car():
    ins = [{"sign": 0, "interval": [0, 0], "distance": 500},
           {"sign": -2, "interval": [1, 1], "street_name": "Congress Ave", "distance": 100}]
    car, hz = scoring.score_route(DOWNTOWN, "car", ins)
    bike, _ = scoring.score_route(DOWNTOWN, "bike", ins)
    base_car, _ = scoring.score_route(DOWNTOWN, "car")
    assert car > base_car and bike > car
    assert any(h["type"] in ("left_turn", "left_turn_major") for h in hz)


def test_quick_turn_after_exit():
    near = [{"sign": 7, "interval": [0, 0], "text": "Take exit 235", "distance": 120},
            {"sign": 2, "interval": [1, 1], "distance": 100}]
    far = [{"sign": 7, "interval": [0, 0], "text": "Take exit 235", "distance": 2000},
           {"sign": 2, "interval": [1, 1], "distance": 100}]
    assert scoring.score_route(EMPTY, "car", near)[0] > scoring.score_route(EMPTY, "car", far)[0]


def test_risk_endpoint():
    c = TestClient(app)
    r = c.get("/risk")
    assert r.status_code == 200
    gj = r.json()
    assert gj["type"] == "FeatureCollection"
    assert all(0 <= f["properties"]["risk"] <= 1 for f in gj["features"])


def test_app_profiles_differ_and_unknown_rejected():
    ins = [{"sign": -2, "interval": [1, 1], "street_name": "Congress Ave", "distance": 100}]
    scores = {p: scoring.score_route(DOWNTOWN, p, ins)[0] for p in ("teen", "elderly", "sensitive_passenger")}
    assert len(set(scores.values())) == 3
    import pytest
    with pytest.raises(ValueError):
        scoring.score_route(DOWNTOWN, "nope")


def test_route_response_helpers():
    assert 0 < scoring.display_risk(67.4) < 1
    assert scoring.to_latlon(DOWNTOWN)[0] == [30.2672, -97.7431]
    fast = [{"type": "left_turn_major"}] * 2 + [{"type": "merge"}]
    safe = [{"type": "merge"}]
    assert scoring.hazards_avoided(fast, safe) == ["2 unprotected left turns"]


def test_risk_min_filter():
    c = TestClient(app)
    full = len(c.get("/risk").json()["features"])
    some = c.get("/risk?min_risk=0.5").json()["features"]
    assert 0 < len(some) < full and all(f["properties"]["risk"] >= 0.5 for f in some)


ROUTE_REQ = {"origin": {"lat": 30.2849, "lng": -97.7341},
             "destination": {"lat": 30.2672, "lng": -97.7431}, "profile": "teen"}
ROUTE_KEYS = {"geometry", "eta_minutes", "distance_km", "risk_score", "risk_events"}
EVENT_TYPES = {"left_turn", "left_turn_major", "quick_exit_turn", "highway_merge", "high_crash_zone"}


def _check_contract(b):
    assert set(b) == {"fastest", "safest", "comparison"}
    assert set(b["comparison"]) == {"minutes_added", "risk_reduction_pct", "summary"}
    for k in ("fastest", "safest"):
        assert set(b[k]) == ROUTE_KEYS
        lat, lng = b[k]["geometry"][0]
        assert 30 < lat < 31 and -98 < lng < -97          # [lat, lng] order
        for e in b[k]["risk_events"]:
            assert set(e) == {"type", "lat", "lng", "description"} and e["type"] in EVENT_TYPES


def test_route_fake_matches_contract(monkeypatch):
    monkeypatch.delenv("GH_URL", raising=False)
    r = TestClient(app).post("/route", json=ROUTE_REQ)
    assert r.status_code == 200 and r.headers["x-data-source"] == "fake"
    b = r.json()
    _check_contract(b)
    assert b["safest"]["eta_minutes"] <= b["fastest"]["eta_minutes"] * 1.25 + 0.1
    assert b["safest"]["risk_score"] <= b["fastest"]["risk_score"]


def test_route_safety_weight_zero_is_fastest():
    r = TestClient(app).post("/route", json={**ROUTE_REQ, "safety_weight": 0})
    b = r.json()
    assert b["safest"]["eta_minutes"] == b["fastest"]["eta_minutes"]
    assert b["comparison"]["minutes_added"] == 0


def test_route_accepts_lon_alias():
    body = {**ROUTE_REQ, "origin": {"lat": 30.2849, "lon": -97.7341}}
    assert TestClient(app).post("/route", json=body).status_code == 200


def test_route_unknown_profile_422():
    r = TestClient(app).post("/route", json={**ROUTE_REQ, "profile": "bogus"})
    assert r.status_code == 422


def test_route_graphhopper_parsing(monkeypatch):
    import httpx
    gh = {"paths": [
        {"distance": 3000, "time": 300000, "instructions": [],
         "points": {"coordinates": [[-97.7341, 30.2849], [-97.7431, 30.2672]]}},
        {"distance": 3300, "time": 330000, "instructions": [],
         "points": {"coordinates": [[-97.7341, 30.2849], [-97.75, 30.28], [-97.7431, 30.2672]]}}]}
    monkeypatch.setenv("GH_URL", "http://gh.test")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
        200, json=gh, request=httpx.Request("POST", "http://gh.test/route")))
    r = TestClient(app).post("/route", json=ROUTE_REQ)
    assert r.status_code == 200 and r.headers["x-data-source"] == "graphhopper"
    _check_contract(r.json())
    assert r.json()["fastest"]["eta_minutes"] == 5.0


def test_crash_risk_standalone():
    pts, events = scoring.crash_risk(DOWNTOWN, "teen")
    assert pts > 0 and events and all(e["type"] == "high_crash_zone" for e in events)
    assert scoring.crash_risk(EMPTY, "teen") == (0.0, [])
