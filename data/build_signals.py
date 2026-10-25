"""Download Austin's active traffic-signal locations to signals.json (list of [lng, lat]).

    python build_signals.py

Source: "Traffic Signals and Pedestrian Signals" (p53x-x73x). Only full traffic signals that are
turned on are kept; pedestrian hybrid beacons (PHB) don't control turning traffic. scoring.py uses
this to tell a left turn at a signalized intersection from one with no signal. A signal does not
guarantee a protected left-turn arrow; the data doesn't say, so this is a proxy.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://data.austintexas.gov/resource/p53x-x73x.json"
OUT = Path(__file__).parent / "signals.json"


def main() -> None:
    query = urllib.parse.urlencode({
        "$select": "location", "$where": "signal_type='TRAFFIC' AND signal_status='TURNED_ON'", "$limit": 20000})
    rows = json.load(urllib.request.urlopen(f"{URL}?{query}", timeout=60))
    pts = [[round(c, 6) for c in r["location"]["coordinates"]] for r in rows if r.get("location")]
    pts.sort()  # stable order so a re-download with the same signals produces an identical file
    OUT.write_text(json.dumps(pts, separators=(",", ":")))
    print(f"wrote {OUT} ({len(pts)} signals)")


if __name__ == "__main__":
    main()
