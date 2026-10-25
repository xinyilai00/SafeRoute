"""Compact the TxDOT Roadway Inventory (Austin area) into txdot_segments.json.

    python build_txdot.py            # needs the 2025 inventory in raw/2025/ (see below)

Source: TxDOT Roadway Inventory, year-end 2025 (https://www.txdot.gov/data-maps/roadway-inventory.html).
Unzip it into data/raw/2025/ so that raw/2025/TxDOT_Roadway_Linework_wAssets.shp exists (about 1.5 GB, so it
is not in git, and neither is the 3 GB download). TxDOT publishes one inventory a year, so this file changes
rarely and is committed; GitHub's weekly refresh reads it but never rebuilds it.

Kept: road classes 1-6 (interstate ... minor collector), which carry a real traffic count (ADT_CUR). Class 7
(local streets) is dropped: about half of those segments carry the same placeholder count of 281 vehicles a
day, so there is no usable exposure. F_SYSTEM codes (checked against the road names in the data):
1 interstate (I-35), 2 other freeway/expressway (SH 130, MoPac, SH 45, US 183), 3 principal arterial,
4 minor arterial, 5 major collector, 6 minor collector.

Each segment: [F_SYSTEM, ADT, speed limit (0 = unknown), lanes, toll (0/1/2), school zone (0/1), miles, coords].
The traffic count is two-way; directions are combined on one line.
"""
import json
import sys
import warnings
from pathlib import Path

import geopandas as gpd

HERE = Path(__file__).parent
SHP = HERE / "raw" / "2025" / "TxDOT_Roadway_Linework_wAssets.shp"
OUT = HERE / "txdot_segments.json"
BBOX = (-98.1, 29.95, -97.3, 30.75)  # same Austin box the backend accepts
PLACEHOLDER_ADT = 281
COLUMNS = ["F_SYSTEM", "ADT_CUR", "ADT_YEAR", "SPD_MAX", "NUM_LANES", "TOLL_FACIL", "SCHOOL_ZN", "LEN_SEC"]
SIMPLIFY_DEG = 0.000015  # about 1.5 m


def main() -> None:
    warnings.filterwarnings("ignore")
    if not SHP.exists():
        raise SystemExit(f"missing {SHP}: unzip TxDOT's 2025 roadway inventory into data/raw/2025/")
    g = gpd.read_file(SHP, bbox=BBOX, columns=COLUMNS, engine="pyogrio")
    g = g[g.F_SYSTEM.between(1, 6) & (g.ADT_CUR != PLACEHOLDER_ADT) & (g.ADT_CUR > 0) & (g.LEN_SEC > 0)]
    segs = []
    for r in g.itertuples():
        geom = r.geometry.simplify(SIMPLIFY_DEG)
        if geom.is_empty or geom.geom_type != "LineString":
            continue
        toll = int(r.TOLL_FACIL) if r.TOLL_FACIL not in (None, "") and str(r.TOLL_FACIL).isdigit() else 0
        segs.append([int(r.F_SYSTEM), int(r.ADT_CUR), int(r.SPD_MAX), int(r.NUM_LANES), toll, int(r.SCHOOL_ZN),
                     round(float(r.LEN_SEC), 4), [[round(x, 5), round(y, 5)] for x, y in geom.coords]])
    OUT.write_text(json.dumps({"meta": {"source": "TxDOT Roadway Inventory year-end 2025", "count": len(segs),
                                        "bbox": BBOX}, "segments": segs}, separators=(",", ":")))
    print(f"wrote {OUT}: {len(segs):,} segments, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    sys.exit(main())
