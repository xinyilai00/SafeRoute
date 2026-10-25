"""Download Austin street pavement condition into street_condition.json.

    python build_pavement.py

Source: City of Austin Public Works street condition scores (28k street segments), the ArcGIS layer
TRANSPORTATION_pw_street_condition_scores. Each segment has the city's own letter grade (A-F), a ride
comfort index and an International Roughness Index (inches/mile). Private streets and TxDOT-maintained
roads (highways) are not covered, so those simply have no pavement data.

Output: [[grade, iri, [[lng, lat], ...]], ...] with 5-decimal coordinates and ~1.5 m simplification.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import LineString

LAYER = ("https://services.arcgis.com/0L95CJ0VTaxqcmED/ArcGIS/rest/services/"
         "TRANSPORTATION_pw_street_condition_scores/FeatureServer/0/query")
OUT = Path(__file__).parent / "street_condition.json"
PAGE = 2000


def fetch_all():
    feats, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": "GRADE,INTL_ROUGHNESS_INDEX_AVG,RIDE_COMFORT_INDEX", "outSR": 4326,
            "f": "geojson", "resultOffset": offset, "resultRecordCount": PAGE})
        d = json.load(urllib.request.urlopen(f"{LAYER}?{q}", timeout=120))
        page = d.get("features", [])
        feats += page
        offset += len(page)
        if not page or (len(page) < PAGE and not d.get("exceededTransferLimit")):
            return feats


def main() -> None:
    feats = fetch_all()
    out = []
    for f in feats:
        p, g = f["properties"], f.get("geometry")
        grade = (p.get("GRADE") or "").strip()
        iri = p.get("INTL_ROUGHNESS_INDEX_AVG")
        if not g or g["type"] != "LineString" or not grade or iri is None:
            continue  # ungraded or missing roughness
        line = LineString(g["coordinates"]).simplify(0.000015)
        out.append([grade, int(iri), [[round(x, 5), round(y, 5)] for x, y in line.coords]])
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT}: {len(out)} of {len(feats)} segments, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
