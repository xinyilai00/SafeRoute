"""Candidate-route providers for POST /route.

A provider returns a list of candidates, each:
    {"coords": [[lon, lat], ...], "minutes": float, "miles": float, "instructions": [...]}
`instructions` use GraphHopper's shape (sign, interval, distance, street_name, text) so
score_route treats fake and real candidates identically.

GH_URL unset  -> FakeProvider (synthetic detours between origin and destination)
GH_URL set    -> GraphHopperProvider (algorithm=alternative_route; needs LM or flexible mode, not CH)
"""
import math
import os

import httpx

M_PER_MILE = 1609.344

# User options for "avoid". A strong preference (priority x0.01 = about 100x less attractive), not a
# ban: a destination only reachable by a toll road or highway still gets a route.
AVOID_OPTIONS = ("tolls", "highways")
AVOID_PRIORITY = "0.01"
AVOID_RULES = {
    "tolls": "toll == ALL",  # not truck-only (HGV) tolls, which don't charge cars
    "highways": "road_class == MOTORWAY || road_class == TRUNK",  # ramps share their road class
}
HIGHWAY_CLASSES = ("motorway", "trunk")


def build_custom_model(avoid=None, blocked=None):
    """One GraphHopper custom model for everything that shapes the route.

    `avoid`: subset of AVOID_OPTIONS. `blocked`: GeoJSON geometry of current road closures
    (priority 0 = never route through). Returns None when there is nothing to say.
    """
    priority = [{"if": AVOID_RULES[a], "multiply_by": AVOID_PRIORITY} for a in AVOID_OPTIONS if a in (avoid or [])]
    model = {}
    if blocked:
        priority.append({"if": "in_closure", "multiply_by": "0"})
        model["areas"] = {"type": "FeatureCollection",
                          "features": [{"id": "closure", "type": "Feature", "properties": {}, "geometry": blocked}]}
    if not priority:
        return None
    model["priority"] = priority
    return model


def share_on(coords, intervals, kinds):
    """Fraction of the route's length whose stretch type is in `kinds` (case-insensitive).

    `intervals` is GraphHopper path details: [[start, end, value], ...] over point indices.
    """
    if not intervals or len(coords) < 2:
        return 0.0
    kinds = {k.lower() for k in kinds}
    segs = [_haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
    total = sum(segs)
    on = sum(sum(segs[a:b]) for a, b, v in intervals if str(v).lower() in kinds)
    return on / total if total else 0.0


def _haversine_m(a, b):
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _densify(waypoints, step_m=60.0):
    """Straight segments between waypoints, with a vertex about every step_m."""
    out, marks = [waypoints[0]], [0]
    for a, b in zip(waypoints, waypoints[1:]):
        n = max(int(_haversine_m(a, b) // step_m), 1)
        for k in range(1, n + 1):
            t = k / n
            out.append([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
        marks.append(len(out) - 1)
    return out, marks


def _length_m(coords):
    return sum(_haversine_m(a, b) for a, b in zip(coords, coords[1:]))


class FakeProvider:
    """Three synthetic routes: direct, a detour bowing left of travel, and one bowing right.

    The crash grid is real, so scores differ for real reasons; the geometry is just not on roads.
    Detours turn left at the first via point, which the scorer penalises, and the "fast" direct
    route gets a highway-style merge, so every penalty path gets exercised.
    """
    name = "fake"
    AVG_MPS = 11.0  # ~25 mph

    def routes(self, origin, destination, blocked=None, avoid=None):
        o = [origin["lng"], origin["lat"]]
        d = [destination["lng"], destination["lat"]]
        dx, dy = d[0] - o[0], d[1] - o[1]
        mid = [(o[0] + d[0]) / 2, (o[1] + d[1]) / 2]
        # unit perpendicular in degrees; 0.004 deg ~ 400 m of bow
        norm = math.hypot(dx, dy) or 1.0
        px, py = -dy / norm, dx / norm
        bow = 0.004
        specs = [
            ("direct", [o, d], 1.0),
            ("left", [o, [mid[0] + px * bow, mid[1] + py * bow], d], 1.0),
            ("right", [o, [mid[0] - px * bow, mid[1] - py * bow], d], 1.0),
        ]
        cands = []
        for label, wps, _ in specs:
            coords, marks = _densify(wps)
            dist = _length_m(coords)
            ins = [{"sign": 0, "interval": [0, marks[1]], "distance": dist / (len(wps) - 1),
                    "street_name": "", "text": "Continue"}]
            if label == "left":
                ins.append({"sign": -2, "interval": [marks[1], marks[-1]], "distance": dist / 2,
                            "street_name": "", "text": "Turn left"})
            elif label == "right":
                ins.append({"sign": 2, "interval": [marks[1], marks[-1]], "distance": dist / 2,
                            "street_name": "", "text": "Turn right"})
            else:
                mid_i = marks[1] // 2
                ins = [{"sign": 7, "interval": [mid_i, marks[1]], "distance": 250,
                        "street_name": "", "text": "Take the exit"},
                       {"sign": -2, "interval": [marks[1] - 3, marks[1]], "distance": 100,
                        "street_name": "", "text": "Turn left"}]
            cands.append({"coords": coords, "minutes": dist / self.AVG_MPS / 60,
                          "miles": dist / M_PER_MILE, "instructions": ins})
        return cands


class GraphHopperProvider:
    name = "graphhopper"

    def __init__(self, url, profile="car", max_paths=5, timeout=15.0):
        self.url, self.profile = url.rstrip("/"), profile
        self.max_paths, self.timeout = max_paths, timeout

    def routes(self, origin, destination, blocked=None, avoid=None):
        """`blocked`: GeoJSON of road closures to route around. `avoid`: subset of AVOID_OPTIONS."""
        avoid = [a for a in AVOID_OPTIONS if a in (avoid or [])]
        body = {
            "points": [[origin["lng"], origin["lat"]], [destination["lng"], destination["lat"]]],
            "profile": self.profile,
            "algorithm": "alternative_route",
            "alternative_route.max_paths": self.max_paths,
            "alternative_route.max_weight_factor": 1.5,  # an alternative may be up to 50% slower than the best
            "alternative_route.max_share_factor": 0.8,   # and may share up to 80% of its length with it
            "instructions": True,
            "points_encoded": False,
            "ch.disable": True,  # alternatives don't work with CH
            # per-stretch road type (highway crash discount, avoid check); toll only when it's needed,
            # so a GraphHopper import without the toll value can't break ordinary requests
            "details": ["road_class", "road_environment"] + (["toll"] if "tolls" in avoid else []),
        }
        custom_model = build_custom_model(avoid, blocked)
        if custom_model:
            body["custom_model"] = custom_model
        r = httpx.post(f"{self.url}/route", json=body, timeout=self.timeout,
                       headers={"ngrok-skip-browser-warning": "true"})  # skips ngrok free-tier interstitial
        r.raise_for_status()
        out = []
        for p in r.json().get("paths", []):
            out.append({"coords": p["points"]["coordinates"],
                        "minutes": p["time"] / 60000.0,
                        "miles": p["distance"] / M_PER_MILE,
                        "instructions": p.get("instructions", []),
                        "road_classes": p.get("details", {}).get("road_class", []),
                        "environments": p.get("details", {}).get("road_environment", []),
                        "tolls": p.get("details", {}).get("toll", [])})
        return out


def get_provider():
    url = os.environ.get("GH_URL")
    if url:
        return GraphHopperProvider(url, os.environ.get("GH_PROFILE", "car"))
    return FakeProvider()
