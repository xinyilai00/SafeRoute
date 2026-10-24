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

RISK_PATH = Path(__file__).parent / "data" / "risk.geojson"
STEP_M = 20.0  # sampling distance along the route

# Per-profile weights. Accepts GraphHopper profile names too (car/bike/foot, etc.).
PROFILES = {
    "car": dict(
        crash=10.0,         # risk points per full 200 m cell-length at risk=1.0
        left=1.5, sharp_left=2.5, slight_left=0.0,
        left_major=2.5,     # extra for a left at a fast-road cell (unprotected-left proxy)
        merge=1.5, roundabout=0.5, u_turn=2.0,
        quick_after_exit=2.5,
    ),
    "bike": dict(
        crash=14.0,
        left=2.5, sharp_left=3.5, slight_left=0.5,
        left_major=4.0,
        merge=3.0, roundabout=3.0, u_turn=2.0,
        quick_after_exit=3.0,
    ),
    "foot": dict(
        crash=12.0,
        left=0.0, sharp_left=0.0, slight_left=0.0,
        left_major=0.0,     # for walkers a "turn" is a crossing; see crossing below
        merge=0.0, roundabout=1.5, u_turn=0.0,
        quick_after_exit=0.0,
        crossing=1.5,       # any turn onto a fast road means crossing it
    ),
}
ALIASES = {"driving": "car", "auto": "car", "cycling": "bike", "bicycle": "bike",
           "walking": "foot", "pedestrian": "foot", "walk": "foot"}

FAST_MPH = 40               # cell speed limit at/above which a turn counts as "major road"
QUICK_EXIT_M = 300.0        # next maneuver this soon after an exit = lane-change scramble
HAZARD_CELL_RISK = 0.6      # crash-cell risk worth flagging on the map
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
        cells[(p["ix"], p["iy"])] = (p["risk"], p.get("speed") or 0.0)
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
    return p if p in PROFILES else "car"


def _lookup(cells, cell_m, x, y):
    return cells.get((int(np.floor(x / cell_m)), int(np.floor(y / cell_m))), (0.0, 0.0))


def score_route(polyline, profile="car", instructions=None, precision=5):
    """Score a candidate route. See module docstring. Returns (risk_score, hazards_list)."""
    cells, cell_m, _ = _grid()
    w = PROFILES[_norm_profile(profile)]
    coords = _coords(polyline, precision)
    hazards = []
    if len(coords) < 2:
        return 0.0, hazards

    xs, ys = _to_utm().transform([c[0] for c in coords], [c[1] for c in coords])
    xy = np.column_stack([xs, ys])
    seg = np.hypot(*np.diff(xy, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]

    def at(d):
        """(x, y) in metres and index of the polyline vertex at distance d."""
        d = min(max(d, 0.0), total)
        i = min(int(np.searchsorted(cum, d, side="right")) - 1, len(seg) - 1)
        t = (d - cum[i]) / seg[i] if seg[i] > 0 else 0.0
        return xy[i] + t * (xy[i + 1] - xy[i])

    # ---- 1. crash risk: walk the line, sample the grid, length-weighted ----
    crash = 0.0
    n = max(int(np.ceil(total / STEP_M)), 1)
    step = total / n
    flagged = set()
    for k in range(n):
        d = (k + 0.5) * step
        x, y = at(d)
        risk, _ = _lookup(cells, cell_m, x, y)
        crash += risk * step / cell_m
        cell = (int(np.floor(x / cell_m)), int(np.floor(y / cell_m)))
        if risk >= HAZARD_CELL_RISK and cell not in flagged:
            flagged.add(cell)
            lon, lat = _to_utm().transform(x, y, direction="INVERSE")
            hazards.append(dict(type="crash_zone", lat=lat, lon=lon, distance_m=round(d),
                                points=round(risk * w["crash"], 2),
                                description=f"High crash-density area (risk {risk:.2f})"))
    score = crash * w["crash"]

    # ---- 2. turn-instruction penalties ----
    prev_exit = None
    for idx, ins in enumerate(instructions or []):
        sign = ins.get("sign", 0)
        start = (ins.get("interval") or [0, 0])[0]
        start = min(max(start, 0), len(xy) - 1)
        x, y = xy[start]
        _, speed = _lookup(cells, cell_m, x, y)
        street = (ins.get("street_name") or "").lower()
        text = (ins.get("text") or "").lower()
        fast = speed >= FAST_MPH or any(h in street for h in MAJOR_NAME_HINTS)
        pts, kind, desc = 0.0, None, None

        if sign in (LEFT, SHARP_LEFT, SLIGHT_LEFT):
            pts = {LEFT: w["left"], SHARP_LEFT: w["sharp_left"], SLIGHT_LEFT: w["slight_left"]}[sign]
            if fast and sign != SLIGHT_LEFT:
                pts += w["left_major"]
                kind, desc = "left_turn_major", "Left turn across a fast/major road"
            elif pts:
                kind, desc = "left_turn", "Left turn"
        elif sign in (KEEP_LEFT, KEEP_RIGHT):
            pts, kind, desc = w["merge"], "merge", "Merge / fork"
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
                kind = kind or "quick_after_exit"
                desc = f"{desc or 'Turn'} only {gap:.0f} m after a highway exit"

        if pts > 0:
            score += pts
            lon, lat = _to_utm().transform(x, y, direction="INVERSE")
            hazards.append(dict(type=kind or "turn", lat=lat, lon=lon,
                                distance_m=round(float(cum[start])),
                                points=round(pts, 2), description=desc or "Turn"))

    hazards.sort(key=lambda h: h["distance_m"])
    return round(float(score), 3), hazards
