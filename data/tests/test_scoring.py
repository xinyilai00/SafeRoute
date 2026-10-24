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


def test_summary_has_no_zero_minute_lead():
    b = TestClient(app).post("/route", json=ROUTE_REQ).json()
    assert not b["comparison"]["summary"].startswith("+0")


def _hot_left_cell():
    """Centre of the cell with the highest left_risk."""
    import json
    from pyproj import Transformer
    f = max(json.loads((Path(__file__).parent.parent / "risk.geojson").read_text())["features"],
            key=lambda x: x["properties"]["left_risk"])
    ring = f["geometry"]["coordinates"][0]
    return (sum(p[0] for p in ring[:4]) / 4, sum(p[1] for p in ring[:4]) / 4)


def test_left_turn_costs_more_where_left_crashes_happen():
    lon, lat = _hot_left_cell()
    line = [[lon - 0.0005, lat], [lon + 0.0005, lat]]
    elon, elat = -98.05, 30.70
    quiet = [[elon - 0.0005, elat], [elon + 0.0005, elat]]
    ins = [{"sign": -2, "interval": [1, 1], "street_name": "Elm St", "distance": 50}]
    hot, hz = scoring.score_route(line, "car", ins)
    base, _ = scoring.score_route(line, "car")
    cold, _ = scoring.score_route(quiet, "car", ins)
    assert hot - base > cold - 0  # the turn adds more at the hot cell than on empty land
    assert any(h["type"] == "left_turn_major" and "left-turn crashes" in h["description"] for h in hz)


def test_pick_safest_respects_min_gain_and_budget():
    from app import _pick_safest
    fast = {"minutes": 10.0, "score": 100.0}
    tiny_gain = {"minutes": 11.0, "score": 98.0}
    big_gain = {"minutes": 11.0, "score": 70.0}
    too_slow = {"minutes": 15.0, "score": 10.0}
    rules = {"max_detour": 1.25, "min_gain": 0.05}
    assert _pick_safest([fast, tiny_gain], fast, 1.0, rules) is fast      # not worth a detour
    assert _pick_safest([fast, big_gain, too_slow], fast, 1.0, rules) is big_gain
    assert _pick_safest([fast, big_gain], fast, 0.0, rules) is fast       # safety_weight 0
    assert _pick_safest([fast, too_slow], fast, 1.0, {"max_detour": 1.6, "min_gain": 0.05}) is too_slow


def test_route_rejects_outside_austin_and_same_point():
    c = TestClient(app)
    far = {**ROUTE_REQ, "destination": {"lat": 32.78, "lng": -96.80}}   # Dallas
    assert c.post("/route", json=far).status_code == 422
    same = {**ROUTE_REQ, "destination": ROUTE_REQ["origin"]}
    assert c.post("/route", json=same).status_code == 422


def test_risk_filter_is_cached_and_consistent():
    c = TestClient(app)
    a, b = c.get("/risk?min_risk=0.5"), c.get("/risk?min_risk=0.5")
    assert a.content == b.content and a.headers["content-type"].startswith("application/geo+json")


def test_curvy_route_costs_more_for_sensitive_passenger():
    import math
    lon0, lat0 = -98.05, 30.70          # empty land: no crash risk, so only curvature differs
    straight = [[lon0 + i * 0.0004, lat0] for i in range(40)]
    wavy = [[lon0 + i * 0.0004, lat0 + 0.0006 * math.sin(i / 3)] for i in range(40)]
    sp_s, _ = scoring.score_route(straight, "sensitive_passenger")
    sp_w, hz = scoring.score_route(wavy, "sensitive_passenger")
    teen_w, _ = scoring.score_route(wavy, "teen")
    assert sp_w > sp_s == 0 and teen_w == 0
    assert any(h["type"] == "winding_road" for h in hz)
