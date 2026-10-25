"""Live traffic from TomTom: real ETAs for each candidate route, and road-closure filtering.

Needs TOMTOM_API_KEY (in the gitignored .env). With no key, or on any TomTom error, everything
here quietly does nothing and /route keeps GraphHopper's free-flow times.

- live ETA: TomTom Calculate Route with traffic=true. The candidate's own points are sent as
  `supportingPoints`, so TomTom times *that* route instead of choosing its own.
- closures: TomTom Traffic Incidents for the Austin box, cached for a couple of minutes. A candidate
  that passes within CLOSURE_BUFFER_M of a "road closed" incident is dropped (unless all of them do).
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping
from shapely.ops import transform, unary_union

import scoring

ROUTING_URL = "https://api.tomtom.com/routing/1/calculateRoute/{o}:{d}/json"
INCIDENTS_URL = "https://api.tomtom.com/traffic/services/5/incidentDetails"
AUSTIN_BBOX = "-98.1,29.95,-97.3,30.75"   # lon/lat box; same area /route accepts
CLOSURE_CATEGORY = 8                       # TomTom iconCategory 8 = road closed
CLOSURE_BUFFER_M = 25.0
BLOCK_BUFFER_M = 25.0      # how far around a closure GraphHopper is told not to route
SUSPECT_RATIO, SUSPECT_EXTRA_MIN = 2.5, 8.0  # live time this far above free-flow = route is probably blocked
MAX_SUPPORT_POINTS = 150                   # TomTom's limit per request
ETA_TTL_S, INCIDENT_TTL_S = 60, 120
TIMEOUT_S = 8.0
MAX_PARALLEL = 3                           # stay under TomTom's free-tier request rate

_lock = threading.Lock()
_eta_cache: dict = {}        # key -> (expires, minutes)
_closure_cache: dict = {}    # "geoms" -> (expires, [shapely geometries in UTM metres])


def enabled() -> bool:
    return bool(os.environ.get("TOMTOM_API_KEY"))


def _support_points(coords):
    """At most MAX_SUPPORT_POINTS evenly spread vertices, always keeping both ends."""
    n = len(coords)
    idx = list(range(n)) if n <= MAX_SUPPORT_POINTS else sorted(
        {round(k * (n - 1) / (MAX_SUPPORT_POINTS - 1)) for k in range(MAX_SUPPORT_POINTS)})
    return [coords[i] for i in idx]


def live_minutes(coords):
    """Traffic-aware travel time (minutes) along `coords` ([[lng, lat], ...]), or None on any failure."""
    pts = _support_points(coords)
    key = hash(tuple((round(x, 5), round(y, 5)) for x, y in pts))
    now = time.time()
    with _lock:
        hit = _eta_cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    (olng, olat), (dlng, dlat) = pts[0], pts[-1]
    minutes = None
    for attempt in range(2):  # one retry, for TomTom's per-second rate limit (429) and brief 5xx
        try:
            r = httpx.post(
                ROUTING_URL.format(o=f"{olat},{olng}", d=f"{dlat},{dlng}"),
                params={"key": os.environ["TOMTOM_API_KEY"], "traffic": "true", "routeType": "fastest"},
                json={"supportingPoints": [{"latitude": lat, "longitude": lng} for lng, lat in pts]},
                timeout=TIMEOUT_S)
            r.raise_for_status()
            minutes = r.json()["routes"][0]["summary"]["travelTimeInSeconds"] / 60.0
            break
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            print(f"live: TomTom ETA failed (HTTP {status})")
            if attempt == 0 and (status == 429 or status >= 500):
                time.sleep(0.7)
                continue
            return None
        except Exception as e:  # network, bad key, no route: fall back to free-flow
            print(f"live: TomTom ETA failed ({type(e).__name__})")
            return None
    if minutes is None:
        return None
    with _lock:
        _eta_cache[key] = (now + ETA_TTL_S, minutes)
    return minutes


def closures():
    """Current road-closure geometries in UTM metres (cached), or [] if unavailable."""
    now = time.time()
    with _lock:
        hit = _closure_cache.get("geoms")
        if hit and hit[0] > now:
            return hit[1]
    try:
        r = httpx.get(INCIDENTS_URL, timeout=TIMEOUT_S, params={
            "key": os.environ["TOMTOM_API_KEY"], "bbox": AUSTIN_BBOX, "language": "en-GB",
            "timeValidityFilter": "present",
            "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory}}}"})
        r.raise_for_status()
        incidents = r.json().get("incidents", [])
    except Exception as e:
        print(f"live: TomTom incidents failed ({type(e).__name__})")
        return []
    to_utm = scoring._to_utm()
    geoms = []
    for inc in incidents:
        if inc["properties"].get("iconCategory") != CLOSURE_CATEGORY:
            continue
        g = inc["geometry"]
        if g["type"] == "Point":
            lng, lat = g["coordinates"]
            x, y = to_utm.transform(lng, lat)
            geoms.append(Point(x, y))
        elif g["type"] == "LineString" and len(g["coordinates"]) >= 2:
            xs, ys = to_utm.transform([c[0] for c in g["coordinates"]], [c[1] for c in g["coordinates"]])
            geoms.append(LineString(list(zip(xs, ys))))
    with _lock:
        _closure_cache["geoms"] = (now + INCIDENT_TTL_S, geoms)
        _closure_cache.pop("area", None)
    return geoms


def closure_area():
    """GeoJSON geometry covering current closures (buffered, simplified, 5-decimal), or None.

    Sent to GraphHopper as a custom-model area with priority 0 so it routes around closed streets.
    """
    geoms = closures()
    if not geoms:
        return None
    with _lock:
        cached = _closure_cache.get("area")
    if cached:
        return cached
    merged = unary_union([g.buffer(BLOCK_BUFFER_M) for g in geoms]).simplify(3)
    inv = Transformer.from_crs(scoring._grid()[2], "EPSG:4326", always_xy=True)
    gj = mapping(transform(lambda x, y, z=None: inv.transform(x, y), merged))

    def rnd(c):
        return [rnd(i) for i in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 5), round(c[1], 5)]

    area = {"type": gj["type"], "coordinates": rnd(gj["coordinates"])}
    with _lock:
        _closure_cache["area"] = area
    return area


def hits_closure(coords, geoms=None) -> bool:
    geoms = closures() if geoms is None else geoms
    if not geoms or len(coords) < 2:
        return False
    xs, ys = scoring._to_utm().transform([c[0] for c in coords], [c[1] for c in coords])
    route = LineString(list(zip(xs, ys)))
    return any(route.distance(g) <= CLOSURE_BUFFER_M for g in geoms)


def apply_live(cands):
    """Replace candidates' minutes with live ones and drop closed routes, in place.

    Keeps GraphHopper's time in c["free_minutes"]. Returns {"live": bool, "dropped": int}.
    A candidate list that is entirely closed is left alone (better a flagged route than none).
    """
    info = {"live": False, "dropped": 0}
    if not enabled() or not cands:
        return info
    with ThreadPoolExecutor(max_workers=min(len(cands), MAX_PARALLEL)) as pool:
        times = list(pool.map(lambda c: live_minutes(c["coords"]), cands))
    for c in cands:
        c["free_minutes"] = c["minutes"]
    if all(m is not None for m in times):  # all live or none: never rank a mix of live and free-flow
        for c, m in zip(cands, times):
            c["minutes"] = m
        info["live"] = True
    geoms = closures()
    if info["live"]:
        for c in cands:  # TomTom takes far longer than free-flow: the route is probably blocked
            c["suspect"] = (c["minutes"] > SUSPECT_RATIO * c["free_minutes"]
                            and c["minutes"] - c["free_minutes"] > SUSPECT_EXTRA_MIN)
    open_ = [c for c in cands if not hits_closure(c["coords"], geoms) and not c.get("suspect")]
    if open_ and len(open_) < len(cands):
        info["dropped"] = len(cands) - len(open_)
        cands[:] = open_
    return info
