"""Route safety scoring.

    from scoring import score_route
    risk, hazards = score_route(route["points"], "car", route["instructions"])

`polyline` is either GraphHopper's encoded polyline string (points_encoded=true,
precision 5; pass `precision=6` through `score_route` if you configured that) or a
list of GeoJSON-order [lon, lat] pairs (points_encoded=false -> route["points"]["coordinates"]).

`road_classes` is GraphHopper's path details (`details=["road_class"]`): [[start, end, "motorway"], ...]
over point indices; highway stretches get their crash risk discounted (see HIGHWAY_CRASH_FACTOR).

`instructions` is GraphHopper's route["instructions"] list (needs `instructions=true`).
It is optional so crash-grid risk can still be scored without it, but the turn
penalties (left turns, merges, roundabouts, quick turns after an exit) need it.

Returns (risk_score, hazards). risk_score is unitless, higher = riskier, and is
meant to be combined as `eta_minutes + w * risk_score`. hazards is a list of dicts
{type, lat, lon, distance_m, points, description} the UI can pin on the map.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from pyproj import Transformer

RISK_PATH = Path(__file__).parent / "risk.geojson"
RATIOS_PATH = Path(__file__).parent / "profile_ratios.json"
SIGNALS_PATH = Path(__file__).parent / "signals.json"
PAVEMENT_PATH = Path(__file__).parent / "street_condition.json"
STEP_M = 20.0  # sampling distance along the route

# Per-profile weights. Accepts GraphHopper profile names too (car/bike/foot, etc.).
PROFILES = {
    "car": dict(
        crash=10.0,         # risk points per full 200 m cell-length at risk=1.0
        left=1.5, sharp_left=2.5, slight_left=0.0,
        left_major=2.5,     # extra for a left at a fast-road cell (unprotected-left proxy)
        curve=0.0,          # points per degree of smooth curving (ride comfort)
        rough=0.0,          # points per km of rough pavement (city grade D/F); ride comfort
        left_crash=4.0,     # x left_risk (0..1): left-turn crash history at the turn's cell
        merge=1.5, roundabout=0.5, u_turn=2.0,
        quick_after_exit=2.5,
    ),
    "bike": dict(
        crash=14.0,
        left=2.5, sharp_left=3.5, slight_left=0.5,
        left_major=4.0,
        left_crash=5.0, curve=0.0, rough=0.0,
        merge=3.0, roundabout=3.0, u_turn=2.0,
        quick_after_exit=3.0,
    ),
    "foot": dict(
        crash=12.0,
        left=0.0, sharp_left=0.0, slight_left=0.0,
        left_major=0.0, left_crash=0.0, curve=0.0, rough=0.0,
                            # for walkers a "turn" is a crossing; see crossing below
        merge=0.0, roundabout=1.5, u_turn=0.0,
        quick_after_exit=0.0,
        crossing=1.5,       # any turn onto a fast road means crossing it
    ),
}
def _measured_ratio(profile, ctype):
    """Measured collision-type ratio for a profile (profile_ratios.json), 1.0 if unavailable."""
    try:
        return json.loads(RATIOS_PATH.read_text())[profile]["ratios"][ctype]
    except Exception:
        return 1.0


# App profiles (wire strings from the iOS app). All are drivers, so they start from "car". Their
# differences are limited to what the data measures (calibrate_profiles.py):
#  - teen / elderly crash risk comes from their own grid layers (risk_teen / risk_elderly), built
#    from each group's measured collision-type mix;
#  - left_crash is scaled by the group's measured left-turn ratio.
# sensitive_passenger has no crash data behind it; its only difference is the ride-comfort curvature
# and rough-pavement penalties. WHERE the pavement is rough comes from the city's own grades (real data);
# how much to penalise curves and rough streets is an assumption. Other maneuver weights stay at the car baseline.
PROFILES["teen"] = {**PROFILES["car"],
                    "left_crash": PROFILES["car"]["left_crash"] * _measured_ratio("teen", "left-turn")}
PROFILES["elderly"] = {**PROFILES["car"],
                       "left_crash": PROFILES["car"]["left_crash"] * _measured_ratio("elderly", "left-turn")}
PROFILES["sensitive_passenger"] = {**PROFILES["car"], "curve": 0.03, "rough": 6.0}
# index into the grid cell tuple (risk, speed, left_risk, risk_teen, risk_elderly)
PROFILE_LAYER = {"teen": 3, "elderly": 4}
ALIASES = {"driving": "car", "auto": "car", "cycling": "bike", "bicycle": "bike",
           "walking": "foot", "pedestrian": "foot", "walk": "foot"}

FAST_MPH = 40               # cell speed limit at/above which a turn counts as "major road"
QUICK_EXIT_M = 300.0        # next maneuver this soon after an exit = lane-change scramble
HAZARD_CELL_RISK = 0.57     # crash-cell risk worth flagging (~top 10% of cells)
LEFT_HOT = 0.55             # left_risk at/above which a left turn is flagged as a left-turn crash hot spot
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
        cells[(p["ix"], p["iy"])] = (p["risk"], p.get("speed") or 0.0, p.get("left_risk") or 0.0,
                                     p.get("risk_teen", p["risk"]), p.get("risk_elderly", p["risk"]))
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
    return cells.get((int(np.floor(x / cell_m)), int(np.floor(y / cell_m))), (0.0, 0.0, 0.0, 0.0, 0.0))


def _project(polyline, precision=5):
    """Polyline -> (UTM points, cumulative metres). Both empty-ish for < 2 points."""
    coords = _coords(polyline, precision)
    if len(coords) < 2:
        return None, None
    xs, ys = _to_utm().transform([c[0] for c in coords], [c[1] for c in coords])
    xy = np.column_stack([xs, ys])
    seg = np.hypot(*np.diff(xy, axis=0).T)
    return xy, np.concatenate([[0.0], np.cumsum(seg)])


def _segment_factors(n_vertices, road_classes, road_environment=None):
    """Per-segment crash multiplier: HIGHWAY_CRASH_FACTOR on motorway/trunk stretches,
    BRIDGE_CRASH_FACTOR on bridges and tunnels (smaller wins), else 1.0."""
    f = np.ones(max(n_vertices - 1, 0))
    for a, b, kind in road_classes or []:
        if str(kind).lower() in HIGHWAY_CLASSES:
            f[a:b] = np.minimum(f[a:b], HIGHWAY_CRASH_FACTOR)
    for a, b, kind in road_environment or []:
        if str(kind).lower() in BRIDGE_CLASSES:
            f[a:b] = np.minimum(f[a:b], BRIDGE_CRASH_FACTOR)
    return f


@lru_cache(maxsize=1)
def _signals():
    """Active traffic signals as UTM metres, shape (n, 2); empty if signals.json is missing."""
    try:
        pts = json.loads(SIGNALS_PATH.read_text())
    except Exception:
        return np.empty((0, 2))
    xs, ys = _to_utm().transform([p[0] for p in pts], [p[1] for p in pts])
    return np.column_stack([xs, ys])


@lru_cache(maxsize=1)
def _pavement():
    """(STRtree of graded street segments in UTM metres, per-segment roughness factor) or None if missing."""
    try:
        from shapely import STRtree
        from shapely.geometry import LineString
        data = json.loads(PAVEMENT_PATH.read_text())
    except Exception:
        return None
    to_utm = _to_utm()
    lines, factors = [], []
    for grade, _iri, coords in data:
        xs, ys = to_utm.transform([c[0] for c in coords], [c[1] for c in coords])
        lines.append(LineString(list(zip(xs, ys))))
        factors.append(ROUGH_GRADES.get(grade, 0.0))
    return STRtree(lines), np.array(factors)


def _rough_km(xy, cum):
    """(effective km of rough pavement along the route, (x, y) of the first rough sample or None)."""
    pav = _pavement()
    if pav is None:
        return 0.0, None
    from shapely.geometry import Point
    tree, factors = pav
    total = cum[-1]
    n = max(int(np.ceil(total / STEP_M)), 1)
    step = total / n
    ds = (np.arange(n) + 0.5) * step
    pts = [Point(np.interp(d, cum, xy[:, 0]), np.interp(d, cum, xy[:, 1])) for d in ds]
    q_idx, t_idx = tree.query_nearest(pts, max_distance=PAVEMENT_MATCH_M, all_matches=False)
    rough = np.zeros(n)
    rough[q_idx] = factors[t_idx]
    first = np.flatnonzero(rough > 0)
    where = (pts[first[0]].x, pts[first[0]].y) if len(first) else None
    return float(rough.sum() * step / 1000.0), where


def _signalized(x, y):
    sig = _signals()
    return bool(len(sig) and np.min(np.hypot(sig[:, 0] - x, sig[:, 1] - y)) <= SIGNAL_RADIUS_M)


# ---- exposure model: crash rate per VEHICLE-MILE from TxDOT traffic counts (see build_exposure.py) ----
# The grid counts crashes per 200 m square, and busy roads simply have more of them. Where a route stretch
# matches a TxDOT road segment with a real traffic count (highways, arterials, collectors), the exposure
# model scores it by that segment's rate per vehicle-mile instead. Elsewhere (mostly local streets, which
# have no real traffic counts) the grid is used as before. Switch with RISK_MODEL=grid|exposure.
SEGMENTS_PATH = Path(__file__).parent / "txdot_segments.json"
RATES_PATH = Path(__file__).parent / "segment_rates.json"
DEFAULT_RISK_MODEL = "exposure"   # per-vehicle rates where TxDOT has traffic counts; RISK_MODEL=grid for the old crash-count grid
SEG_MATCH_M = 15.0            # a route sample this close to a TxDOT segment takes that segment's rate
METERS_PER_MILE = 1609.344
# Points per mile for one unit of rate (severity-weighted crashes per 100M vehicle-miles). Calibrated so that the
# average minor-arterial / collector stretch scores the same under both models (see calibrate_exposure.py), which
# keeps the two parts of a route on one scale. Highways then score far lower per mile because their measured
# per-vehicle rate is far lower.
EXPOSURE_POINTS_PER_RATE = 0.0846
HOT_SEGMENT_RATIO = 2.0       # flag a segment whose rate is at least this many times its road class's average


def _use_exposure() -> bool:
    return os.environ.get("RISK_MODEL", DEFAULT_RISK_MODEL).lower() == "exposure"


@lru_cache(maxsize=1)
def _segments():
    """TxDOT segments with per-vehicle crash rates, as an STRtree in UTM metres; None if the files are missing."""
    try:
        from shapely import STRtree
        from shapely.geometry import LineString
        data = json.loads(SEGMENTS_PATH.read_text())["segments"]
        rates = json.loads(RATES_PATH.read_text())
    except Exception:
        return None
    if len(rates.get("rate", [])) != len(data):
        return None                                  # rates were built for a different segment file
    to_utm = _to_utm()
    lines = []
    for seg in data:
        xs, ys = to_utm.transform([c[0] for c in seg[7]], [c[1] for c in seg[7]])
        lines.append(LineString(list(zip(xs, ys))))
    klass = np.array([seg[0] for seg in data])
    class_rate = {int(k): v for k, v in rates["meta"]["class_rate_per_100M_vmt"].items()}
    return {"tree": STRtree(lines), "F": klass, "speed": np.array([seg[2] for seg in data]),
            "lanes": np.array([seg[3] for seg in data]),
            "rate": {"general": np.array(rates["rate"]), "teen": np.array(rates["teen"]), "elderly": np.array(rates["elderly"])},
            "class_rate": np.array([class_rate.get(int(f), np.nan) for f in klass])}


def _exposure_model(profile_name):
    """What _crash_component needs for the exposure model, or None when it is off or unavailable."""
    if not _use_exposure():
        return None
    segs = _segments()
    return None if segs is None else {"seg": segs, "which": profile_name if profile_name in ("teen", "elderly") else "general"}


def _match_segments(px, py, hw_mask, segs):
    """Index of the TxDOT segment under each sample point (-1 = none).

    Frontage roads run beside freeways, so a sample on a road GraphHopper does NOT call motorway/trunk is not
    allowed to take a freeway-class segment's rate (class 1 or 2).
    """
    from shapely import points
    q, t = segs["tree"].query_nearest(points(px, py), max_distance=SEG_MATCH_M, all_matches=False)
    out = np.full(len(px), -1, dtype=int)
    out[q] = t
    if hw_mask is not None:
        freeway = np.isin(segs["F"][np.maximum(out, 0)], (1, 2)) & (out >= 0)
        out[freeway & ~hw_mask] = -1
    return out


def _highway_mask(n_vertices, road_classes, step_idx):
    """Per sample: does GraphHopper call this stretch motorway/trunk? None when no road classes were given."""
    if not road_classes:
        return None
    on = np.zeros(max(n_vertices - 1, 0), dtype=bool)
    for a, b, kind in road_classes:
        if str(kind).lower() in HIGHWAY_CLASSES:
            on[a:b] = True
    return on[step_idx]


def _crash_component(xy, cum, w, seg_factor=None, layer=0, expo=None, road_classes=None):
    """Walk the line, sample every STEP_M, length-weighted. -> (points, events).

    Grid model: points = crash_weight x sum(cell risk x factor x step / 200 m). With `expo` (exposure model),
    samples that match a TxDOT segment use that segment's rate per vehicle-mile instead.
    """
    cells, cell_m, _ = _grid()
    seg_len = np.diff(cum)
    total = cum[-1]
    n = max(int(np.ceil(total / STEP_M)), 1)
    step = total / n
    ds = (np.arange(n) + 0.5) * step
    px, py = np.interp(ds, cum, xy[:, 0]), np.interp(ds, cum, xy[:, 1])
    idx = np.minimum(np.searchsorted(cum, ds, side="right") - 1, len(seg_len) - 1)
    hit = None
    if expo is not None:
        hit = _match_segments(px, py, _highway_mask(len(xy), road_classes, idx), expo["seg"])
    crash, crash_expo, hazards, flagged = 0.0, 0.0, [], set()
    for k in range(n):
        x, y, i, d = px[k], py[k], idx[k], ds[k]
        j = hit[k] if hit is not None else -1
        if j >= 0:
            segs = expo["seg"]
            rate = segs["rate"][expo["which"]][j]
            crash_expo += EXPOSURE_POINTS_PER_RATE * rate * step / METERS_PER_MILE
            ratio = rate / segs["class_rate"][j] if segs["class_rate"][j] > 0 else 0.0
            if ratio >= HOT_SEGMENT_RATIO and ("seg", int(j)) not in flagged:
                flagged.add(("seg", int(j)))
                lon, lat = _to_utm().transform(x, y, direction="INVERSE")
                hazards.append(dict(type="high_crash_zone", lat=lat, lon=lon, distance_m=round(d),
                                    points=round(EXPOSURE_POINTS_PER_RATE * rate * cell_m / METERS_PER_MILE, 2),
                                    description=f"Crash rate {ratio:.1f}x the usual for this type of road"))
            continue
        risk = _lookup(cells, cell_m, x, y)[layer] * (seg_factor[i] if seg_factor is not None else 1.0)
        crash += risk * step / cell_m
        cell = (int(np.floor(x / cell_m)), int(np.floor(y / cell_m)))
        if risk >= HAZARD_CELL_RISK and cell not in flagged:
            flagged.add(cell)
            lon, lat = _to_utm().transform(x, y, direction="INVERSE")
            hazards.append(dict(type="high_crash_zone", lat=lat, lon=lon, distance_m=round(d),
                                points=round(risk * w["crash"], 2),
                                description=f"High crash-density area (risk {risk:.2f})"))
    return crash * w["crash"] + crash_expo, hazards


# Raw crash counts over-penalise highways: they carry far more traffic, so a cell on I-35 has many
# crashes without each trip being riskier per mile. Stretches GraphHopper reports as these road
# classes get their grid crash risk scaled by this factor (maneuvers like merges are still penalised).
HIGHWAY_CLASSES = {"motorway", "trunk"}
HIGHWAY_CRASH_FACTOR = 0.6

# Bridges and tunnels: the grid square under an overpass is mostly the road below (e.g. a street
# bridge over I-35), so crash risk on those stretches is scaled down. Where a stretch is both a
# highway and a bridge the smaller factor wins (they are not multiplied). An assumption, not measured.
BRIDGE_CLASSES = {"bridge", "tunnel"}
BRIDGE_CRASH_FACTOR = 0.5
SIGNAL_RADIUS_M = 35.0      # a left turn this close to a traffic signal counts as signalized

# City of Austin street condition: the city's own letter grades. Share of a stretch counted as "rough".
ROUGH_GRADES = {"F": 1.0, "D": 0.5}
PAVEMENT_MATCH_M = 15.0     # a route sample this close to a graded street segment takes that segment's grade

CURVE_STEP_M = 25.0         # resampling distance for curvature
CURVE_MAX_STEP_DEG = 25.0   # a bigger heading change within one step is a corner, scored as a turn instead


def _curve_degrees(xy, cum):
    """Total heading change (degrees) along smooth bends, ignoring corners."""
    total = cum[-1]
    if total < 2 * CURVE_STEP_M:
        return 0.0
    ds = np.arange(0.0, total, CURVE_STEP_M)
    px = np.interp(ds, cum, xy[:, 0])
    py = np.interp(ds, cum, xy[:, 1])
    heading = np.degrees(np.arctan2(np.diff(py), np.diff(px)))
    delta = np.abs((np.diff(heading) + 180.0) % 360.0 - 180.0)
    return float(delta[delta < CURVE_MAX_STEP_DEG].sum())


def crash_risk(polyline, profile="car", precision=5, road_classes=None, road_environment=None):
    """Crash-grid risk only (no turn penalties): (points, [high_crash_zone events]).

    `polyline`: GeoJSON-order [[lng, lat], ...] (GraphHopper points_encoded=false), a GeoJSON
    LineString dict, or an encoded polyline string. NOT [lat, lng].
    """
    name = _norm_profile(profile)
    w = PROFILES[name]
    xy, cum = _project(polyline, precision)
    if xy is None:
        return 0.0, []
    score, hazards = _crash_component(xy, cum, w, _segment_factors(len(xy), road_classes, road_environment),
                                      PROFILE_LAYER.get(name, 0), _exposure_model(name), road_classes)
    return round(float(score), 3), hazards


def score_route(polyline, profile="car", instructions=None, precision=5, road_classes=None,
                road_environment=None):
    """Crash risk + maneuver penalties. See module docstring. Returns (risk_score, hazards_list)."""
    name = _norm_profile(profile)
    w = PROFILES[name]
    xy, cum = _project(polyline, precision)
    if xy is None:
        return 0.0, []
    cells, cell_m, _ = _grid()
    score, hazards = _crash_component(xy, cum, w, _segment_factors(len(xy), road_classes, road_environment),
                                      PROFILE_LAYER.get(name, 0), _exposure_model(name), road_classes)

    # ---- ride comfort: smooth curving, for profiles that care ----
    curve_pts = w["curve"] * _curve_degrees(xy, cum)
    if curve_pts >= 1.0:
        score += curve_pts
        lon0, lat0 = _to_utm().transform(*xy[0], direction="INVERSE")
        hazards.append(dict(type="winding_road", lat=lat0, lon=lon0, distance_m=0,
                            points=round(curve_pts, 2), description="Winding road with sharp curves"))

    # ---- 2. turn-instruction penalties ----
    # ---- ride comfort: rough pavement (city grades D/F), for profiles that care ----
    if w["rough"] > 0:
        rough_km, where = _rough_km(xy, cum)
        rough_pts = w["rough"] * rough_km
        if rough_pts >= 1.0 and where:
            score += rough_pts
            lon0, lat0 = _to_utm().transform(*where, direction="INVERSE")
            hazards.append(dict(type="rough_road", lat=lat0, lon=lon0, distance_m=0, points=round(rough_pts, 2),
                                description=f"{rough_km:.1f} km of rough pavement (city grade D/F)"))

    prev_exit = None
    for idx, ins in enumerate(instructions or []):
        sign = ins.get("sign", 0)
        start = (ins.get("interval") or [0, 0])[0]
        start = min(max(start, 0), len(xy) - 1)
        x, y = xy[start]
        _, speed, left_risk = _lookup(cells, cell_m, x, y)[:3]
        street = (ins.get("street_name") or "").lower()
        text = (ins.get("text") or "").lower()
        fast = speed >= FAST_MPH or any(h in street for h in MAJOR_NAME_HINTS)
        pts, kind, desc = 0.0, None, None

        if sign in (LEFT, SHARP_LEFT, SLIGHT_LEFT):
            pts = {LEFT: w["left"], SHARP_LEFT: w["sharp_left"], SLIGHT_LEFT: w["slight_left"]}[sign]
            if sign != SLIGHT_LEFT:
                pts += w["left_crash"] * left_risk
                hot = left_risk >= LEFT_HOT
                signalized = _signalized(x, y)
                unprotected = fast and not signalized   # fast road, no traffic signal at the turn
                if unprotected:
                    pts += w["left_major"]
                if unprotected or hot:
                    kind = "left_turn_major"
                    desc = ("Left turn where left-turn crashes are common" if hot
                            else "Left turn across a fast road with no traffic signal")
                elif pts:
                    kind = "left_turn"
                    desc = "Left turn at a traffic signal" if signalized else "Left turn"
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
    "winding_road": ("winding road", "winding roads"),
    "rough_road": ("rough-pavement stretch", "rough-pavement stretches"),
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
