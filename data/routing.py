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

    def routes(self, origin, destination):
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

    def __init__(self, url, profile="car", max_paths=4, timeout=15.0):
        self.url, self.profile = url.rstrip("/"), profile
        self.max_paths, self.timeout = max_paths, timeout

    def routes(self, origin, destination):
        body = {
            "points": [[origin["lng"], origin["lat"]], [destination["lng"], destination["lat"]]],
            "profile": self.profile,
            "algorithm": "alternative_route",
            "alternative_route.max_paths": self.max_paths,
            "instructions": True,
            "points_encoded": False,
            "ch.disable": True,  # alternatives don't work with CH
            "details": ["road_class"],  # per-stretch road type, used to discount highway crash counts
        }
        r = httpx.post(f"{self.url}/route", json=body, timeout=self.timeout,
                       headers={"ngrok-skip-browser-warning": "true"})  # skips ngrok free-tier interstitial
        r.raise_for_status()
        out = []
        for p in r.json().get("paths", []):
            out.append({"coords": p["points"]["coordinates"],
                        "minutes": p["time"] / 60000.0,
                        "miles": p["distance"] / M_PER_MILE,
                        "instructions": p.get("instructions", []),
                        "road_classes": p.get("details", {}).get("road_class", [])})
        return out


def get_provider():
    url = os.environ.get("GH_URL")
    if url:
        return GraphHopperProvider(url, os.environ.get("GH_PROFILE", "car"))
    return FakeProvider()
