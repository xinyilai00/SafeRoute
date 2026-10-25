import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402
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
    rules = {"max_detour": 1.25, "min_gain": 0.05, "beta": 1.0}
    assert _pick_safest([fast, tiny_gain], fast, 1.0, rules) is fast      # not worth a detour
    assert _pick_safest([fast, big_gain, too_slow], fast, 1.0, rules) is big_gain
    assert _pick_safest([fast, big_gain], fast, 0.0, rules) is fast       # safety_weight 0
    assert _pick_safest([fast, too_slow], fast, 1.0, {**rules, "max_detour": 1.6}) is too_slow


def test_pick_safest_keeps_the_faster_road_when_time_matters():
    from app import _pick_safest
    fast = {"minutes": 20.0, "score": 100.0}
    slow_safe = {"minutes": 23.6, "score": 85.0}    # 18% slower for 15% less risk: not worth it
    good_trade = {"minutes": 22.0, "score": 70.0}   # 10% slower for 30% less risk: worth it
    rules = {"max_detour": 1.25, "min_gain": 0.03, "beta": 1.0}
    assert _pick_safest([fast, slow_safe], fast, 1.0, rules) is fast
    assert _pick_safest([fast, slow_safe, good_trade], fast, 1.0, rules) is good_trade
    # a profile that pays more time for safety (beta 1.5) takes the slower one
    assert _pick_safest([fast, slow_safe], fast, 1.0, {**rules, "beta": 2.0}) is slow_safe


def test_highway_crash_risk_is_discounted():
    n = len(DOWNTOWN_LINE := [[-97.7431, 30.2672 + i * 0.0002] for i in range(90)])
    plain, _ = scoring.score_route(DOWNTOWN_LINE, "car")
    hwy, hz = scoring.score_route(DOWNTOWN_LINE, "car", road_classes=[[0, n - 1, "motorway"]])
    local, _ = scoring.score_route(DOWNTOWN_LINE, "car", road_classes=[[0, n - 1, "residential"]])
    assert hwy < plain * 0.8 and local == plain
    assert len(hz) <= len(scoring.score_route(DOWNTOWN_LINE, "car")[1])


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


# ---------- live traffic (TomTom), all network calls patched ----------

def test_support_points_cap_and_ends():
    import live
    coords = [[-97.7 + i * 1e-4, 30.2] for i in range(1000)]
    pts = live._support_points(coords)
    assert len(pts) <= live.MAX_SUPPORT_POINTS and pts[0] == coords[0] and pts[-1] == coords[-1]
    short = coords[:10]
    assert live._support_points(short) == short


def test_apply_live_replaces_minutes_and_drops_closed(monkeypatch):
    import live
    from shapely.geometry import Point
    from pyproj import Transformer
    monkeypatch.setenv("TOMTOM_API_KEY", "x")
    a = {"coords": [[-97.7431, 30.2672], [-97.7431, 30.2700]], "minutes": 5.0}
    b = {"coords": [[-97.7300, 30.2672], [-97.7300, 30.2700]], "minutes": 6.0}
    x, y = scoring._to_utm().transform(-97.7431, 30.2686)         # closure sits on route a
    monkeypatch.setattr(live, "closures", lambda: [Point(x, y)])
    monkeypatch.setattr(live, "live_minutes", lambda coords: 12.0 if coords is a["coords"] else 7.5)
    cands = [a, b]
    info = live.apply_live(cands)
    assert info == {"live": True, "dropped": 1}
    assert cands == [b] and b["minutes"] == 7.5 and b["free_minutes"] == 6.0


def test_apply_live_keeps_all_closed_and_never_mixes_times(monkeypatch):
    import live
    from shapely.geometry import Point
    monkeypatch.setenv("TOMTOM_API_KEY", "x")
    a = {"coords": [[-97.7431, 30.2672], [-97.7431, 30.2700]], "minutes": 5.0}
    b = {"coords": [[-97.7431, 30.2672], [-97.7431, 30.2700]], "minutes": 6.0}
    x, y = scoring._to_utm().transform(-97.7431, 30.2686)
    monkeypatch.setattr(live, "closures", lambda: [Point(x, y)])
    monkeypatch.setattr(live, "live_minutes", lambda coords: None)   # TomTom down
    cands = [a, b]
    info = live.apply_live(cands)
    assert info == {"live": False, "dropped": 0} and len(cands) == 2   # all closed: kept
    assert a["minutes"] == 5.0 and b["minutes"] == 6.0                 # free-flow untouched


def test_apply_live_is_noop_without_key(monkeypatch):
    import live
    monkeypatch.setenv("TOMTOM_API_KEY", "")
    cands = [{"coords": [[-97.7, 30.2], [-97.71, 30.21]], "minutes": 5.0}]
    assert live.apply_live(cands) == {"live": False, "dropped": 0} and cands[0]["minutes"] == 5.0


def test_suspect_slow_routes_are_dropped(monkeypatch):
    import live
    monkeypatch.setenv("TOMTOM_API_KEY", "x")
    good = {"coords": [[-97.74, 30.26], [-97.74, 30.27]], "minutes": 4.0}
    blocked = {"coords": [[-97.73, 30.26], [-97.73, 30.27]], "minutes": 4.0}
    monkeypatch.setattr(live, "closures", lambda: [])
    monkeypatch.setattr(live, "live_minutes", lambda coords: 8.0 if coords is good["coords"] else 28.0)
    cands = [good, blocked]
    info = live.apply_live(cands)
    assert cands == [good] and info["dropped"] == 1


def test_closure_area_is_geojson_and_small(monkeypatch):
    import live
    from shapely.geometry import LineString
    x1, y1 = scoring._to_utm().transform(-97.7431, 30.2672)
    monkeypatch.setattr(live, "closures", lambda: [LineString([(x1, y1), (x1 + 120, y1 + 40)])])
    live._closure_cache.pop("area", None)
    area = live.closure_area()
    assert area["type"] in ("Polygon", "MultiPolygon")
    lng, lat = area["coordinates"][0][0][:2] if area["type"] == "Polygon" else area["coordinates"][0][0][0]
    assert -98 < lng < -97 and 30 < lat < 31
    live._closure_cache.pop("area", None)


def _http_error(status):
    import httpx
    req = httpx.Request("POST", "http://gh.test/route")
    return httpx.HTTPStatusError("boom", request=req, response=httpx.Response(status, request=req))


def test_route_retries_without_blocked_area(monkeypatch):
    import live, routing
    calls = []

    class P:
        name = "graphhopper"

        def routes(self, o, d, blocked=None, avoid=None):
            calls.append((bool(blocked), tuple(avoid or [])))
            if blocked:
                raise _http_error(400)  # e.g. an endpoint inside the blocked area
            return routing.FakeProvider().routes(o, d)
    monkeypatch.setattr(routing, "get_provider", lambda: P())
    monkeypatch.setattr(live, "enabled", lambda: True)
    monkeypatch.setattr(live, "closure_area", lambda: {"type": "Polygon", "coordinates": []})
    monkeypatch.setattr(live, "apply_live", lambda cands: {"live": False, "dropped": 0})
    r = TestClient(app).post("/route", json=ROUTE_REQ)
    assert r.status_code == 200 and calls == [(True, ()), (False, ())]

# ---------- avoid tolls / highways ----------

def test_build_custom_model_variants():
    import routing
    assert routing.build_custom_model(None, None) is None and routing.build_custom_model([], None) is None
    m = routing.build_custom_model(["tolls"])
    assert m == {"priority": [{"if": "toll == ALL", "multiply_by": "0.01"}]}
    h = routing.build_custom_model(["highways"])
    assert h["priority"][0]["if"] == "road_class == MOTORWAY || road_class == TRUNK"
    both = routing.build_custom_model(["highways", "tolls"])
    assert [r["if"] for r in both["priority"]] == ["toll == ALL", "road_class == MOTORWAY || road_class == TRUNK"]
    area = {"type": "Polygon", "coordinates": []}
    merged = routing.build_custom_model(["tolls"], area)           # one model: avoid rules AND closures
    assert [r["if"] for r in merged["priority"]] == ["toll == ALL", "in_closure"]
    assert merged["priority"][-1]["multiply_by"] == "0" and merged["areas"]["features"][0]["geometry"] == area
    only_closure = routing.build_custom_model(None, area)
    assert [r["if"] for r in only_closure["priority"]] == ["in_closure"]


def test_share_on():
    import routing
    coords = [[-97.7 + i * 0.001, 30.2] for i in range(11)]       # 10 equal segments
    assert routing.share_on(coords, [[0, 4, "MOTORWAY"], [4, 10, "residential"]], ["motorway"]) == pytest.approx(0.4, abs=1e-6)
    assert routing.share_on(coords, [], ["motorway"]) == 0.0
    assert routing.share_on(coords, [[0, 10, "all"]], ["ALL"]) == pytest.approx(1.0)


def test_graphhopper_request_body(monkeypatch):
    import httpx, routing
    sent = {}

    def fake_post(url, json=None, **kw):
        sent.update(json)
        return httpx.Response(200, json={"paths": []}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    gh = routing.GraphHopperProvider("http://gh.test")
    o, d = {"lat": 30.28, "lng": -97.73}, {"lat": 30.26, "lng": -97.74}
    gh.routes(o, d)
    assert "custom_model" not in sent and sent["details"] == ["road_class", "road_environment"]
    assert sent["points"] == [[-97.73, 30.28], [-97.74, 30.26]] and sent["alternative_route.max_paths"] == 5
    gh.routes(o, d, avoid=["tolls"])
    assert sent["details"] == ["road_class", "road_environment", "toll"] and sent["custom_model"]["priority"][0]["if"] == "toll == ALL"
    gh.routes(o, d, blocked={"type": "Polygon", "coordinates": []}, avoid=["highways"])
    assert len(sent["custom_model"]["priority"]) == 2 and "areas" in sent["custom_model"]


class _GHStub:
    """GraphHopper stand-in: 400s for any custom model containing `reject`, else returns one route."""
    name = "graphhopper"

    def __init__(self, reject=None, tolls=None, road_classes=None):
        self.reject, self.calls = reject, []
        self.tolls, self.road_classes = tolls or [], road_classes or []

    def routes(self, o, d, blocked=None, avoid=None):
        avoid = list(avoid or [])
        self.calls.append((bool(blocked), tuple(avoid)))
        if self.reject and self.reject in avoid:
            raise _http_error(400)
        import routing
        c = routing.FakeProvider().routes(o, d)[0]
        n = len(c["coords"])
        c["tolls"] = [[0, n - 1, v] for v in self.tolls]
        c["road_classes"] = [[0, n - 1, v] for v in self.road_classes]
        return [c]


def _route_with(monkeypatch, stub, body):
    import live, routing
    monkeypatch.setattr(routing, "get_provider", lambda: stub)
    monkeypatch.setattr(live, "enabled", lambda: False)
    return TestClient(app).post("/route", json=body)


def test_avoid_applied_and_reported(monkeypatch):
    stub = _GHStub(tolls=["no"], road_classes=["residential"])
    r = _route_with(monkeypatch, stub, {**ROUTE_REQ, "avoid": ["tolls", "highways", "tolls"]})
    assert r.status_code == 200 and r.headers["x-avoid-applied"] == "tolls,highways"
    assert stub.calls == [(False, ("tolls", "highways"))]
    assert "couldn't" not in r.json()["comparison"]["summary"]


def test_avoid_note_when_route_still_uses_tolls(monkeypatch):
    r = _route_with(monkeypatch, _GHStub(tolls=["all"]), {**ROUTE_REQ, "avoid": ["tolls"]})
    assert "couldn't fully avoid tolls (100% of the route)" in r.json()["comparison"]["summary"]


def test_avoid_rejected_by_engine_is_reported_not_hidden(monkeypatch):
    stub = _GHStub(reject="tolls")
    r = _route_with(monkeypatch, stub, {**ROUTE_REQ, "avoid": ["tolls"]})
    assert r.status_code == 200 and r.headers["x-avoid-applied"] == "none"
    assert "couldn't avoid tolls" in r.json()["comparison"]["summary"]
    assert stub.calls == [(False, ("tolls",)), (False, ())]


def test_non_400_engine_error_is_not_retried(monkeypatch):
    class Down(_GHStub):
        def routes(self, o, d, blocked=None, avoid=None):
            self.calls.append(1)
            raise _http_error(503)
    stub = Down()
    r = _route_with(monkeypatch, stub, {**ROUTE_REQ, "avoid": ["tolls"]})
    assert r.status_code == 502 and len(stub.calls) == 1


def test_avoid_validation(monkeypatch):
    c = TestClient(app)
    assert c.post("/route", json={**ROUTE_REQ, "avoid": ["ferries"]}).status_code == 422
    assert c.post("/route", json={**ROUTE_REQ, "avoid": "tolls"}).status_code == 422
    assert c.post("/route", json=ROUTE_REQ).status_code == 200            # avoid is optional
    r = c.post("/route", json={**ROUTE_REQ, "avoid": ["tolls"]})          # fake provider: accepted, no note
    assert r.status_code == 200 and "couldn't" not in r.json()["comparison"]["summary"]


def test_live_minutes_retries_once_on_rate_limit(monkeypatch):
    import httpx, live
    monkeypatch.setenv("TOMTOM_API_KEY", "x")
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    live._eta_cache.clear()
    calls = []

    def fake_post(url, **kw):
        calls.append(1)
        req = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(429, request=req)
        return httpx.Response(200, request=req, json={"routes": [{"summary": {"travelTimeInSeconds": 600}}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    assert live.live_minutes([[-97.7, 30.2], [-97.71, 30.21]]) == 10.0 and len(calls) == 2
    live._eta_cache.clear()
    calls.clear()
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (calls.append(1), httpx.Response(400, request=httpx.Request("POST", url)))[1])
    assert live.live_minutes([[-97.7, 30.2], [-97.71, 30.22]]) is None and len(calls) == 1   # 400: no retry
    live._eta_cache.clear()


# ---------- measured profiles, signals, bridges ----------

def test_profiles_differ_in_maneuver_strictness():
    P = scoring.PROFILES
    assert P["teen"]["merge"] == P["car"]["merge"]
    for k in scoring.MANEUVER_KEYS:                                   # elderly strictest, then sensitive, then teen
        assert P["elderly"][k] > P["sensitive_passenger"][k] > P["teen"][k] == P["car"][k]
    R = __import__("app").ROUTING_RULES
    assert R["elderly"]["beta"] > R["sensitive_passenger"]["beta"] > R["teen"]["beta"]
    assert R["elderly"]["min_gain"] < R["sensitive_passenger"]["min_gain"] < R["teen"]["min_gain"]


def test_profiles_differ_only_by_measured_things():
    P = scoring.PROFILES
    ratios = json.loads((Path(__file__).parent.parent / "profile_ratios.json").read_text())
    assert P["teen"]["left_crash"] == pytest.approx(P["car"]["left_crash"] * ratios["teen"]["ratios"]["left-turn"])
    assert P["elderly"]["left_crash"] == pytest.approx(P["car"]["left_crash"] * ratios["elderly"]["ratios"]["left-turn"])
    ignore = {"left_crash", "curve", "rough", *scoring.MANEUVER_KEYS}    # maneuver strictness is a product choice, tested above
    for name in ("teen", "elderly", "sensitive_passenger"):          # everything else is the car baseline
        assert {k: v for k, v in P[name].items() if k not in ignore} == {k: v for k, v in P["car"].items() if k not in ignore}
    assert P["sensitive_passenger"]["curve"] > 0 and P["teen"]["curve"] == P["elderly"]["curve"] == 0
    assert P["sensitive_passenger"]["rough"] > 0 and P["teen"]["rough"] == P["elderly"]["rough"] == P["car"]["rough"] == 0


def test_teen_and_elderly_use_their_own_grid_layers():
    gj = json.loads((Path(__file__).parent.parent / "risk.geojson").read_text())
    f = max(gj["features"], key=lambda x: abs(x["properties"]["risk_teen"] - x["properties"]["risk_elderly"]))
    p = f["properties"]
    assert p["risk_teen"] != p["risk_elderly"]
    ring = f["geometry"]["coordinates"][0]
    lon = sum(c[0] for c in ring[:4]) / 4
    lat = sum(c[1] for c in ring[:4]) / 4
    line = [[lon - 0.0004, lat], [lon + 0.0004, lat]]
    teen, _ = scoring.crash_risk(line, "teen")
    eld, _ = scoring.crash_risk(line, "elderly")
    car, _ = scoring.crash_risk(line, "car")
    assert (teen > eld) == (p["risk_teen"] > p["risk_elderly"]) and car > 0


def test_left_turn_signalized_vs_unsignalized():
    sig = json.loads((Path(__file__).parent.parent / "signals.json").read_text())
    assert len(sig) > 500
    lon, lat = sig[0]
    ins = [{"sign": -2, "interval": [0, 0], "street_name": "Test Pkwy", "distance": 100}]
    # same fast street name, one turn at a signal, one far from any signal
    at_signal, hz1 = scoring.score_route([[lon, lat], [lon + 0.0005, lat]], "car", ins)
    no_signal, hz2 = scoring.score_route([[-98.05, 30.70], [-98.0495, 30.70]], "car", ins)
    lefts = [h for h in hz1 if h["type"].startswith("left_turn")]
    assert lefts and not any("no traffic signal" in h["description"] for h in lefts)   # signalized: not "unprotected"
    assert any(h["type"] == "left_turn_major" and "no traffic signal" in h["description"] for h in hz2)
    assert scoring._signalized(*scoring._signals()[0]) and not scoring._signalized(*scoring._to_utm().transform(-98.05, 30.70))


def test_bridge_discount_and_min_rule():
    f = scoring._segment_factors(11, [[0, 4, "motorway"]], [[2, 8, "bridge"], [8, 10, "tunnel"]])
    assert f[0] == f[1] == scoring.HIGHWAY_CRASH_FACTOR           # highway only
    assert f[2] == f[3] == min(scoring.HIGHWAY_CRASH_FACTOR, scoring.BRIDGE_CRASH_FACTOR)  # both: smaller wins, not product
    assert f[5] == scoring.BRIDGE_CRASH_FACTOR and f[8] == scoring.BRIDGE_CRASH_FACTOR
    line = [[-97.7431, 30.2672 + i * 0.0002] for i in range(60)]
    n = len(line)
    plain, _ = scoring.score_route(line, "car")
    over, _ = scoring.score_route(line, "car", road_environment=[[0, n - 1, "bridge"]])
    assert over < plain * 0.7


# ---------- weather heads-up ----------

def test_weather_classify_and_headers(monkeypatch):
    import weather
    assert weather._classify({"precipitation": 0.4, "weather_code": 61, "visibility": 20000, "temperature_2m": 18})["raining"]
    assert weather._classify({"precipitation": 0, "weather_code": 95})["raining"]            # thunderstorm
    clear = weather._classify({"precipitation": 0, "rain": 0, "weather_code": 1, "visibility": 25000, "temperature_2m": 20})
    assert not clear["raining"] and not clear["low_visibility"] and not clear["freezing"]
    assert weather._classify({"visibility": 1200, "temperature_2m": -3})["low_visibility"]
    assert weather._classify({"visibility": 1200, "temperature_2m": -3})["freezing"]
    monkeypatch.setattr(weather, "current", lambda: {"raining": True, "low_visibility": False, "freezing": False, "source": "x"})
    r = TestClient(app).post("/route", json=ROUTE_REQ)
    assert r.headers["x-weather"] == "rain" and float(r.headers["x-weather-crash-ratio"]) > 1.2
    monkeypatch.setattr(weather, "current", lambda: {"raining": False, "low_visibility": False, "freezing": False, "source": "x"})
    r = TestClient(app).post("/route", json=ROUTE_REQ)
    assert r.headers["x-weather"] == "dry" and "x-weather-crash-ratio" not in r.headers
    monkeypatch.setattr(weather, "current", lambda: None)
    assert TestClient(app).post("/route", json=ROUTE_REQ).headers["x-weather"] == "unknown"


def test_weather_current_caches_and_survives_failure(monkeypatch):
    import httpx, weather
    monkeypatch.delenv("WEATHER_DISABLED", raising=False)
    weather._cache.update(expires=0.0, value=None)
    calls = []

    def fake_get(url, **kw):
        calls.append(1)
        req = httpx.Request("GET", url)
        return httpx.Response(200, request=req, json={"current": {"precipitation": 1.2, "weather_code": 63,
                                                                  "visibility": 3000, "temperature_2m": 15}})
    monkeypatch.setattr(httpx, "get", fake_get)
    first, second = weather.current(), weather.current()
    assert first == second and first["raining"] and first["low_visibility"] and len(calls) == 1   # cached
    weather._cache.update(expires=0.0, value=None)
    monkeypatch.setattr(httpx, "get", lambda url, **kw: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert weather.current() is None                                                              # failure -> no heads-up
    weather._cache.update(expires=0.0, value=None)


# ---------- pavement (ride comfort) ----------

def _graded_segment(grade):
    data = json.loads((Path(__file__).parent.parent / "street_condition.json").read_text())
    return max((d for d in data if d[0] == grade), key=lambda d: len(d[2]))[2]


def test_rough_pavement_only_penalised_for_sensitive_passenger():
    rough, smooth = _graded_segment("F"), _graded_segment("A")
    sp, hz = scoring.score_route(rough, "sensitive_passenger")
    car, hz_car = scoring.score_route(rough, "car")
    assert any(h["type"] == "rough_road" for h in hz) and not any(h["type"] == "rough_road" for h in hz_car)
    assert sp > car
    assert not any(h["type"] == "rough_road" for h in scoring.score_route(smooth, "sensitive_passenger")[1])
    assert not any(h["type"] == "rough_road" for h in scoring.score_route(rough, "teen")[1])


def test_rough_km_uses_city_grades_and_ignores_far_routes():
    f = _graded_segment("F")
    xy, cum = scoring._project(f)
    km, where = scoring._rough_km(xy, cum)
    assert km > 0 and where is not None and abs(km - cum[-1] / 1000) < 0.2 * cum[-1] / 1000 + 0.02  # grade F counts fully
    far = [[-98.05, 30.70], [-98.05, 30.71]]                     # empty land: no graded streets
    xy2, cum2 = scoring._project(far)
    assert scoring._rough_km(xy2, cum2)[0] == 0.0
