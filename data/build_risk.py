"""Build data/risk.geojson: a 200 m risk grid over Austin from Vision Zero crash data.

    python build_risk.py            # download CSV if missing, then build
    python build_risk.py --refresh  # force re-download
    python build_risk.py --since 2016

Pipeline: crashes -> UTM 14N (metres) -> 200 m cells -> weighted sum per cell
-> log-scaled and normalised to 0..1 -> GeoJSON in WGS84.
"""
import argparse
import json
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CSV_PATH = HERE / "raw" / "crashes.csv"
OUT_PATH = HERE / "risk.geojson"

# "Austin Crash Report Data - Crash Level Records" (Vision Zero), Socrata id y2wy-tgr5
CSV_URL = "https://data.austintexas.gov/resource/y2wy-tgr5.csv"
COLUMNS = ("id,crash_timestamp_ct,latitude,longitude,crash_sev_id,crash_fatal_fl,"
           "death_cnt,crash_speed_limit,is_deleted,collsn_desc,est_comp_cost_crash_based")

CELL_M = 200
UTM = "EPSG:32614"  # UTM zone 14N, metres; covers Austin
# Sanity box so geocoding junk (0,0 etc.) and far-flung rows don't stretch the grid.
LON_RANGE, LAT_RANGE = (-98.1, -97.3), (29.95, 30.75)

# Collision-type groups from `collsn_desc`; used for the profile-specific grids (see calibrate_profiles.py).
TYPES = ("left-turn", "single-vehicle", "rear-end/stopped", "angle", "opposite-direction", "other")
PROFILE_RATIOS_PATH = HERE / "profile_ratios.json"


def crash_type(desc) -> str:
    d = str(desc or "").upper()
    if "LEFT TURN" in d or "TURNING LEFT" in d:
        return "left-turn"
    if d.startswith("ONE MOTOR VEHICLE"):
        return "single-vehicle"
    if "REAR-END" in d or "ONE STRAIGHT-ONE STOPPED" in d:
        return "rear-end/stopped"
    if d.startswith("ANGLE"):
        return "angle"
    if d.startswith("OPPOSITE"):
        return "opposite-direction"
    return "other"


def load_profile_multipliers() -> dict:
    """{"teen": {type: multiplier}, "elderly": {...}} from profile_ratios.json, or {} if not built yet."""
    if not PROFILE_RATIOS_PATH.exists():
        return {}
    ratios = json.loads(PROFILE_RATIOS_PATH.read_text())
    return {p: {t: ratios[p]["ratios"][t] for t in TYPES} for p in ("teen", "elderly") if p in ratios}


# CRIS crash_sev_id: 4 killed, 1 suspected serious, 2 non-incapacitating,
# 3 possible injury, 5 not injured, 0 unknown. Used with --weights severity.
SEVERITY_WEIGHT = {4: 10.0, 1: 6.0, 2: 2.0, 3: 1.0, 5: 0.5, 0: 0.5}
# --weights cost: the city's own estimated comprehensive cost per crash (about $25k for a
# no-injury crash up to ~$4.4M for a fatal one), in units of that $25k baseline. backtest.py shows
# it predicts later crashes slightly worse than severity weights (rare fatals add noise).
COST_UNIT = 25_000.0
# Collision descriptions that involve a left turn ("ANGLE - ONE STRAIGHT-ONE LEFT TURN",
# "ONE MOTOR VEHICLE - TURNING LEFT", ...). Drives the left-turn crash layer.
LEFT_TURN_RE = "LEFT TURN|TURNING LEFT"


def download(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode({"$select": COLUMNS, "$limit": 1_000_000})
    print(f"downloading {CSV_URL} ...")
    tmp = path.with_suffix(".tmp")  # download to a temp file so a failed download never leaves a half-written CSV
    urllib.request.urlretrieve(f"{CSV_URL}?{query}", tmp)
    tmp.replace(path)
    print(f"saved {path} ({path.stat().st_size / 1e6:.1f} MB)")


def load_crashes(path: Path, since: int | None = None, until: int | None = None,
                 weights: str = "severity", halflife: float | None = None) -> gpd.GeoDataFrame:
    df = pd.read_csv(path)
    df = df[df["is_deleted"].astype(str).str.lower() != "true"]
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[df["longitude"].between(*LON_RANGE) & df["latitude"].between(*LAT_RANGE)]
    df["date"] = pd.to_datetime(df["crash_timestamp_ct"], errors="coerce")
    if since:
        df = df[df["date"].dt.year >= since]
    if until:
        df = df[df["date"].dt.year <= until]

    if weights == "cost":
        # a missing cost counts as one baseline (no-injury) crash
        df["weight"] = (df["est_comp_cost_crash_based"] / COST_UNIT).fillna(1.0)
    else:
        w = df["crash_sev_id"].map(SEVERITY_WEIGHT).fillna(0.5)
        fatal = df["crash_fatal_fl"].astype(str).str.lower().eq("true") | (df["death_cnt"].fillna(0) > 0)
        df["weight"] = np.where(fatal, SEVERITY_WEIGHT[4], w)
    if halflife:  # a crash `halflife` years older than the newest counts half as much
        age = df["date"].dt.year.max() - df["date"].dt.year
        df["weight"] = df["weight"] * 0.5 ** (age / halflife)
    df["is_left"] = df["collsn_desc"].fillna("").str.contains(LEFT_TURN_RE)
    df["ctype"] = df["collsn_desc"].map(crash_type)

    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs="EPSG:4326"
    ).to_crs(UTM)
    return gdf


def build_grid(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # Cell index is floor(x / 200): absolute, so score_route can recompute it from a point.
    ix = np.floor(gdf.geometry.x / CELL_M).astype(int)
    iy = np.floor(gdf.geometry.y / CELL_M).astype(int)
    cells = (
        pd.DataFrame({
            "ix": ix, "iy": iy, "weight": gdf["weight"].values,
            "left_weight": np.where(gdf["is_left"], gdf["weight"], 0.0),
            "left_n": gdf["is_left"].astype(int).values,
            "speed": gdf["crash_speed_limit"].where(gdf["crash_speed_limit"] > 0).values,
        })
        .groupby(["ix", "iy"])
        .agg(crashes=("weight", "size"), weighted=("weight", "sum"),
             left_crashes=("left_n", "sum"), left_weighted=("left_weight", "sum"),
             speed=("speed", "median"))
        .reset_index()
    )
    # Per collision type weighted sums, for the teen / elderly layers
    by_type = (
        pd.DataFrame({"ix": ix, "iy": iy, "ctype": gdf["ctype"].values, "weight": gdf["weight"].values})
        .pivot_table(index=["ix", "iy"], columns="ctype", values="weight", aggfunc="sum", fill_value=0.0)
        .reindex(columns=list(TYPES), fill_value=0.0)
        .reset_index()
    )
    cells = cells.merge(by_type, on=["ix", "iy"], how="left")
    for profile, mult in load_profile_multipliers().items():
        w_profile = sum(cells[t] * mult[t] for t in TYPES)
        scaled_p = np.log1p(w_profile)
        cells[f"risk_{profile}"] = (scaled_p / scaled_p.max()).round(4)
    cells = cells.drop(columns=list(TYPES))

    # Raw sums are heavy-tailed (a few downtown/highway cells dominate), so scale on log
    # before normalising or the heatmap would be one red dot on a blue map.
    scaled = np.log1p(cells["weighted"])
    cells["risk"] = (scaled / scaled.max()).round(4)
    # Left-turn crash layer, scaled the same way (0 where no left-turn crash happened).
    left_scaled = np.log1p(cells["left_weighted"])
    cells["left_risk"] = (left_scaled / left_scaled.max()).round(4)
    cells["speed"] = cells["speed"].round(0)

    from shapely.geometry import box
    geoms = [box(x * CELL_M, y * CELL_M, (x + 1) * CELL_M, (y + 1) * CELL_M)
             for x, y in zip(cells["ix"], cells["iy"])]
    return gpd.GeoDataFrame(cells, geometry=geoms, crs=UTM)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download the CSV")
    ap.add_argument("--since", type=int, help="only crashes from this year on")
    ap.add_argument("--weights", choices=("cost", "severity"), default="severity",
                    help="crash weighting: hand-set severity weights (default; best in backtest.py) "
                         "or the city's cost estimates")
    ap.add_argument("--halflife", type=float, default=5.0,
                    help="recency half-life in years (default 5; 0 = all years equal)")
    args = ap.parse_args()

    if args.refresh or not CSV_PATH.exists():
        download(CSV_PATH)
    crashes = load_crashes(CSV_PATH, args.since, weights=args.weights, halflife=args.halflife)
    print(f"{len(crashes):,} geocoded crashes, "
          f"{crashes['date'].min():%Y-%m-%d} to {crashes['date'].max():%Y-%m-%d}")

    grid = build_grid(crashes).to_crs("EPSG:4326")
    grid["weighted"] = grid["weighted"].round(1)
    grid["left_weighted"] = grid["left_weighted"].round(1)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    gj = json.loads(grid.to_json(drop_id=True, na="null", to_wgs84=True))
    # foreign member so consumers can index cells without geometry math
    gj["grid"] = {"cell_m": CELL_M, "crs": UTM}
    # provenance, used by refresh.py to find which crashes are newer than this grid
    gj["meta"] = {"data_through": crashes["date"].max().isoformat(), "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "crashes": int(len(crashes)), "cells": int(len(grid)), "halflife": args.halflife, "weights": args.weights}
    OUT_PATH.write_text(json.dumps(gj, separators=(",", ":")))
    print(f"wrote {OUT_PATH} ({len(grid):,} non-empty cells, "
          f"{OUT_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
