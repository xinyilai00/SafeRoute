"""Measure how teen and older drivers' serious/fatal crashes differ from everyone's, by collision type.

    python calibrate_profiles.py

Austin's victim table (`Crash Victim Demographic Records`, xecs-rpy9) only covers people hurt in
serious or fatal crashes: ~9.4k people, ~420 crashes with a teen driver victim, ~520 with a driver
65+. That is far too few for a grid per age group (~9.6k squares), but plenty for a handful of
GLOBAL ratios: for each collision type, how much more (or less) common is it in this group's crashes
than in all serious/fatal crashes? Those ratios become per-type multipliers in the teen and elderly
grids (build_risk.py), so the profiles differ by measured amounts instead of hand-set weights.

Ratios are shrunk toward 1 with k pseudo-crashes so small groups can't produce wild values:
    ratio = (observed + k) / (expected + k)
Writes profile_ratios.json (small, committed, so builds are reproducible).
"""
import csv
import io
import json
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from build_risk import CSV_PATH, TYPES, crash_type, download

HERE = Path(__file__).parent
PERSONS_PATH = HERE / "raw" / "persons.csv"
OUT_PATH = HERE / "profile_ratios.json"
PERSONS_URL = "https://data.austintexas.gov/resource/xecs-rpy9.csv"
GROUPS = {"teen": (15, 19), "elderly": (65, 120)}
SHRINK_K = 20.0


def fetch_persons(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode({
        "$select": "crash_pk,prsn_age,is_primary_person,is_deleted", "$limit": 2_000_000})
    urllib.request.urlretrieve(f"{PERSONS_URL}?{query}", path)


def main() -> None:
    if not CSV_PATH.exists():
        download(CSV_PATH)
    if not PERSONS_PATH.exists():
        fetch_persons(PERSONS_PATH)

    # serious (1) or fatal (4) crashes and their collision type
    ksi = {}
    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            if r["crash_sev_id"] in ("1", "4"):
                ksi[r["id"]] = crash_type(r["collsn_desc"])
    base = Counter(ksi.values())
    n_base = len(ksi)

    persons = list(csv.DictReader(open(PERSONS_PATH)))
    out = {"baseline": {"crashes": n_base, "share": {t: base[t] / n_base for t in TYPES}},
           "shrink_k": SHRINK_K,
           "note": "ratios = shrunk (observed+k)/(expected+k) of collision-type share vs all serious/fatal crashes"}
    for group, (lo, hi) in GROUPS.items():
        crashes = {p["crash_pk"] for p in persons
                   if p["is_primary_person"] == "true" and p["prsn_age"].isdigit()
                   and lo <= int(p["prsn_age"]) <= hi and p["crash_pk"] in ksi}
        counts = Counter(ksi[c] for c in crashes)
        n = len(crashes)
        ratios = {t: round((counts[t] + SHRINK_K) / (n * base[t] / n_base + SHRINK_K), 3) for t in TYPES}
        out[group] = {"age_range": [lo, hi], "crashes": n, "counts": {t: counts[t] for t in TYPES},
                      "raw_ratios": {t: round((counts[t] / n) / (base[t] / n_base), 3) for t in TYPES},
                      "ratios": ratios}
        print(f"{group}: {n} crashes")
        for t in TYPES:
            print(f"   {t:20s} observed {counts[t]:4d}  raw ratio {out[group]['raw_ratios'][t]:4.2f}  -> used {ratios[t]:4.2f}")
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
