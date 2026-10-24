"""Route safety scoring.

    from scoring import score_route
    risk, hazards = score_route(route["points"], "car", route["instructions"])

`polyline` is either GraphHopper's encoded polyline string (points_encoded=true,
precision 5; pass `precision=6` through `score_route` if you configured that) or a
list of GeoJSON-order [lon, lat] pairs (points_encoded=false -> route["points"]["coordinates"]).

`instructions` is GraphHopper's route["instructions"] list (needs `instructions=true`).
It is optional so crash-grid risk can still be scored without it, but the turn
penalties (left turns, merges, roundabouts, quick turns after an exit) need it.

Returns (risk_score, hazards). risk_score is unitless, higher = riskier, and is
meant to be combined as `eta_minutes + w * risk_score`. hazards is a list of dicts
{type, lat, lon, distance_m, points, description} the UI can pin on the map.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from pyproj import Transformer

RISK_PATH = Path(__file__).parent / "risk.geojson"
STEP_M = 20.0  # sampling distance along the route

# Per-profile weights. Accepts GraphHopper profile names too (car/bike/foot, etc.).
PROFILES = {
    "car": dict(
        crash=10.0,         # risk points per full 200 m cell-length at risk=1.0
        left=1.5, sharp_left=2.5, slight_left=0.0,
        left_major=2.5,     # extra for a left at a fast-road cell (unprotected-left proxy)
        left_crash=4.0,     # x left_risk (0..1): left-turn crash history at the turn's cell
        merge=1.5, roundabout=0.5, u_turn=2.0,
        quick_after_exit=2.5,
    ),
    "bike": dict(
        crash=14.0,
        left=2.5, sharp_left=3.5, slight_left=0.5,
        left_major=4.0,
        left_crash=5.0,
        merge=3.0, roundabout=3.0, u_turn=2.0,
        quick_after_exit=3.0,
    ),
    "foot": dict(
        crash=12.0,
        left=0.0, sharp_left=0.0, slight_left=0.0,
        left_major=0.0, left_crash=0.0,
                            # for walkers a "turn" is a crossing; see crossing below
        merge=0.0, roundabout=1.5, u_turn=0.0,
        quick_after_exit=0.0,
        crossing=1.5,       # any turn onto a fast road means crossing it
    ),
}
# App profiles (wire strings from the iOS app). All are drivers, so they start from "car".
PROFILES["teen"] = {**PROFILES["car"],
                    "crash": 11.0, "merge": 2.5, "left_major": 3.5, "roundabout": 1.0,
                    "quick_after_exit": 3.5}           # inexperienced: merges, fast lefts
PROFILES["elderly"] = {**PROFILES["car"],
                       "crash": 11.0, "left": 2.5, "sharp_left": 3.5, "left_major": 4.0, "left_crash": 6.0,
                       "merge": 2.0, "roundabout": 1.5, "u_turn": 3.0}  # lefts and complexity
PROFILES["sensitive_passenger"] = {**PROFILES["car"],
                                   "crash": 12.0, "sharp_left": 3.5, "merge": 2.0,
                                   "roundabout": 1.5, "u_turn": 3.0}    # smooth, fewer hard turns
ALIASES = {"driving": "car", "auto": "car", "cycling": "bike", "bicycle": "bike",
           "walking": "foot", "pedestrian": "foot", "walk": "foot"}

FAST_MPH = 40               # cell speed limit at/above which a turn counts as "major road"
QUICK_EXIT_M = 300.0        # next maneuver this soon after an exit = lane-change scramble
HAZARD_CELL_RISK = 0.62     # crash-cell risk worth flagging (~top 10% of cells)
LEFT_HOT = 0.65             # left_risk at/above which a left turn is flagged as a left-turn crash hot spot
MAJOR_NAME_HINTS = ("hwy", "highway", "pkwy", "parkway", "expy", "expressway", "fwy",
                    "freeway", "blvd", "loop", "ih ", "ih-", "us ", "fm ", "sh ")

# GraphHopper instruction signs
U_TURN_LEFT, KEEP_LEFT, SHARP_LEFT, LEFT, SLIGHT_LEFT = -8, -7, -3, -2, -1
SLIGHT_RIGHT, RIGHT, SHARP_RIGHT, ROUNDABOUT, KEEP_RIGHT, U_TURN_RIGHT = 1, 2, 3, 6, 7, 8
U_TURN_UNKNOWN = -98


@lru_cache(maxsize=1)
def _grid():
    gj = json.loads(RISK_PATH.read_text())
    cell_m = gj["grid"]["cell_m"]
    cells = {}
    for f in gj["features"]:
        p = f["properties"]
        cells[(p["ix"], p["iy"])] = (p["risk"], p.get("speed") or 0.0, p.get("left_risk") or 0.0)
    return cells, cell_m, gj["grid"]["crs"]


@lru_cache(maxsize=1)
def _to_utm():
    return Transformer.from_crs("EPSG:4326", _grid()[2], always_xy=True)


def decode_polyline(s: str, precision: int = 5) -> list[tuple[float, float]]:
    """Google/GraphHopper encoded polyline -> [(lon, lat), ...]."""
    out, i, lat, lon, f = [], 0, 0, 0, 10.0 ** precision
    while i < len(s):
        for axis in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += d
            else:
                lon += d
        out.append((lon / f, lat / f))
    return out


def _coords(polyline, precision):
    if isinstance(polyline, str):
        return decode_polyline(polyline, precision)
    if isinstance(polyline, dict):  # a GeoJSON LineString straight from GraphHopper
        polyline = polyline["coordinates"]
    return [(c[0], c[1]) for c in polyline]  # drops optional elevation


def _norm_profile(profile: str) -> str:
    p = (profile or "car").lower()
    p = ALIASES.get(p, p)
    if p not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; expected one of {sorted(PROFILES)}")
    return p


def _lookup(cells, cell_m, x, y):
    return cells.get((int(np.floor(x / cell_m)), int(np.floor(y / cell_m))), (0.0, 0.0, 0.0))


def _project(polyline, precision=5):
    """Polyline -> (UTM points, cumulative metres). Both empty-ish for < 2 points."""
    coords = _coords(polyline, precision)
    if len(coords) < 2:
        return None, None
    xs, ys = _to_utm().transform([c[0] for c in coords], [c[1] for c in coords])
    xy = np.column_stack([xs, ys])
    seg = np.hypot(*np.diff(xy, axis=0).T)
    return xy, np.concatenate([[0.0], np.cumsum(seg)])


def _crash_component(xy, cum, w):
    """Walk the line, sample the grid every STEP_M, length-weighted. -> (points, events)."""
    cells, cell_m, _ = _grid()
    seg_len = np.diff(cum)
    total = cum[-1]

    def at(d):
        d = min(max(d, 0.0), total)
        i = min(int(np.searchsorted(cum, d, side="right")) - 1, len(seg_len) - 1)
        t = (d - cum[i]) / seg_len[i] if seg_len[i] > 0 else 0.0
        return xy[i] + t * (xy[i + 1] - xy[i])

    crash, hazards, flagged = 0.0, [], set()
    n = max(int(np.ceil(total / STEP_M)), 1)
    step = total / n
    for k in range(n):
        d = (k + 0.5) * step
        x, y = at(d)
        risk = _lookup(cells, cell_m, x, y)[0]
        crash += risk * step / cell_m
        cell = (int(np.floor(x / cell_m)), int(np.floor(y / cell_m)))
        if risk >= HAZARD_CELL_RISK and cell not in flagged:
            flagged.add(cell)
            lon, lat = _to_utm().transform(x, y, direction="INVERSE")
            hazards.append(dict(type="high_crash_zone", lat=lat, lon=lon, distance_m=round(d),
                                points=round(risk * w["crash"], 2),
                                description=f"High crash-density area (risk {risk:.2f})"))
    return crash * w["crash"], hazards


def crash_risk(polyline, profile="car", precision=5):
    """Crash-grid risk only (no turn penalties): (points, [high_crash_zone events]).

    `polyline`: GeoJSON-order [[lng, lat], ...] (GraphHopper points_encoded=false), a GeoJSON
    LineString dict, or an encoded polyline string. NOT [lat, lng].
    """
    w = PROFILES[_norm_profile(profile)]
    xy, cum = _project(polyline, precision)
    if xy is None:
        return 0.0, []
    score, hazards = _crash_component(xy, cum, w)
    return round(float(score), 3), hazards


def score_route(polyline, profile="car", instructions=None, precision=5):
    """Crash risk + maneuver penalties. See module docstring. Returns (risk_score, hazards_list)."""
    w = PROFILES[_norm_profile(profile)]
    xy, cum = _project(polyline, precision)
    if xy is None:
        return 0.0, []
    cells, cell_m, _ = _grid()
    score, hazards = _crash_component(xy, cum, w)

    # ---- 2. turn-instruction penalties ----
    prev_exit = None
    for idx, ins in enumerate(instructions or []):
        sign = ins.get("sign", 0)
        start = (ins.get("interval") or [0, 0])[0]
        start = min(max(start, 0), len(xy) - 1)
        x, y = xy[start]
        _, speed, left_risk = _lookup(cells, cell_m, x, y)
        street = (ins.get("street_name") or "").lower()
        text = (ins.get("text") or "").lower()
        fast = speed >= FAST_MPH or any(h in street for h in MAJOR_NAME_HINTS)
        pts, kind, desc = 0.0, None, None

        if sign in (LEFT, SHARP_LEFT, SLIGHT_LEFT):
            pts = {LEFT: w["left"], SHARP_LEFT: w["sharp_left"], SLIGHT_LEFT: w["slight_left"]}[sign]
            if sign != SLIGHT_LEFT:
                pts += w["left_crash"] * left_risk
                hot = left_risk >= LEFT_HOT
                if fast:
                    pts += w["left_major"]
                if fast or hot:
                    kind = "left_turn_major"
                    desc = ("Left turn where left-turn crashes are common" if hot
                            else "Left turn across a fast/major road")
                elif pts:
                    kind, desc = "left_turn", "Left turn"
            elif pts:
                kind, desc = "left_turn", "Left turn"
        elif sign in (KEEP_LEFT, KEEP_RIGHT):
            pts, kind, desc = w["merge"], "highway_merge", "Merge / fork"
            if "exit" in text or "ramp" in text or "ramp" in street:
                prev_exit = idx
                desc = "Highway exit / ramp"
        elif sign == ROUNDABOUT:
            pts, kind, desc = w["roundabout"], "roundabout", "Roundabout"
        elif sign in (U_TURN_LEFT, U_TURN_RIGHT, U_TURN_UNKNOWN):
            pts, kind, desc = w["u_turn"], "u_turn", "U-turn"
        elif sign in (RIGHT, SHARP_RIGHT, SLIGHT_RIGHT) and fast and "crossing" in w:
            pts, kind, desc = w["crossing"], "crossing", "Crossing a fast road"

        if prev_exit is not None and idx == prev_exit + 1 and sign != 0:
            # the exit instruction's `distance` is how far until this next maneuver
            gap = instructions[prev_exit].get("distance", float("inf"))
            if gap < QUICK_EXIT_M:
                q = w["quick_after_exit"] * (1.0 - gap / QUICK_EXIT_M + 0.5)
                pts += q
                kind = kind or "quick_exit_turn"
                desc = f"{desc or 'Turn'} only {gap:.0f} m after a highway exit"

        if pts > 0:
            score += pts
            lon, lat = _to_utm().transform(x, y, direction="INVERSE")
            hazards.append(dict(type=kind or "turn", lat=lat, lon=lon,
                                distance_m=round(float(cum[start])),
                                points=round(pts, 2), description=desc or "Turn"))

    hazards.sort(key=lambda h: h["distance_m"])
    return round(float(score), 3), hazards


# ---------- helpers for building the /route response the iOS app expects ----------

RISK_HALF = 100.0  # raw score at which the 0..1 display risk reaches 0.5; tune after real trips


def display_risk(score: float) -> float:
    """Raw score (unbounded) -> 0..1 for the app's `risk` field."""
    return round(score / (score + RISK_HALF), 3)


def to_latlon(polyline, precision=5):
    """Any accepted polyline input -> [[lat, lon], ...], the order the iOS app draws."""
    return [[lat, lon] for lon, lat in _coords(polyline, precision)]


_AVOID_LABELS = {
    "left_turn_major": ("unprotected left turn", "unprotected left turns"),
    "left_turn": ("left turn", "left turns"),
    "highway_merge": ("highway merge", "highway merges"),
    "quick_exit_turn": ("rushed turn after an exit", "rushed turns after an exit"),
    "roundabout": ("roundabout", "roundabouts"),
    "u_turn": ("U-turn", "U-turns"),
    "high_crash_zone": ("high-crash zone", "high-crash zones"),
    "crossing": ("crossing of a fast road", "crossings of fast roads"),
}


def hazards_avoided(fast_hazards, safe_hazards):
    """Strings like "2 unprotected left turns" for hazards on the fastest route but not the safest."""
    def count(hs):
        c = {}
        for h in hs:
            c[h["type"]] = c.get(h["type"], 0) + 1
        return c
    fast, safe = count(fast_hazards), count(safe_hazards)
    out = []
    for kind, (one, many) in _AVOID_LABELS.items():
        n = fast.get(kind, 0) - safe.get(kind, 0)
        if n > 0:
            out.append(f"{n} {one if n == 1 else many}")
    return out
