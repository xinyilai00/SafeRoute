"""Crash rate per VEHICLE-MILE for every TxDOT road segment -> segment_rates.json.

    python build_exposure.py              # rates from crashes through the last complete year
    python build_exposure.py --validate   # also test, on held-out years, how much smoothing predicts best

Why: the 200 m crash grid counts crashes per square, and busy roads simply have more crashes. What a driver
cares about is risk per trip, i.e. crashes per vehicle-mile. TxDOT's inventory gives every highway and
arterial a traffic count (ADT_CUR), so a segment's rate = (crashes matched to it) / (vehicles x miles x days).

Method
* Each crash is matched to the nearest classed road segment within MATCH_M metres.
* Crash weight = severity weight x recency (half-life 5 years), the same as the grid. Exposure uses the same
  recency weights, so the rate is a recency-weighted average. TxDOT's count is the 2025 volume, applied to
  all years (traffic grew, so older exposure is a little understated; that biases all classes alike).
* Short segments have few crashes, so raw rates are noisy. Empirical-Bayes smoothing pulls each rate toward
  its road class's pooled rate:  rate = (crashes + M x class_rate) / (exposure + M), with M in units of
  100 million vehicle-miles. M is chosen by `--validate` (held-out Poisson log-likelihood), not by hand.
* Three variants: general, teen and elderly (crash types weighted by the measured ratios in
  profile_ratios.json, like the grid's profile layers).

Rates are severity-weighted crashes per 100M vehicle-miles. Output is aligned by index with txdot_segments.json.
"""
import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import LineString

import build_risk as b

HERE = Path(__file__).parent
SEGMENTS_PATH = HERE / "txdot_segments.json"
RATES_PATH = HERE / "segment_rates.json"
MATCH_M = 15.0
FIRST_YEAR = 2014
HALFLIFE = 5.0
PRIOR_M = 0.002         # smoothing strength (100M vehicle-miles), chosen on 2022-2023 held out from a 2021 fit, i.e. without looking at 2024-2025 (0.005 was within 0.2% of it)
M_GRID = (0.0, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 1e9)


def load_segments(path: Path = SEGMENTS_PATH) -> tuple[pd.DataFrame, list]:
    """(attributes, lines in UTM metres) in file order."""
    d = json.loads(path.read_text())["segments"]
    attrs = pd.DataFrame([s[:7] for s in d], columns=["F", "adt", "speed", "lanes", "toll", "school", "miles"])
    to_utm = Transformer.from_crs("EPSG:4326", b.UTM, always_xy=True)
    lines = []
    for s in d:
        xs, ys = to_utm.transform([c[0] for c in s[7]], [c[1] for c in s[7]])
        lines.append(LineString(list(zip(xs, ys))))
    return attrs, lines


def match_crashes(lines: list, crashes) -> np.ndarray:
    """Index of the nearest segment within MATCH_M metres for each crash, -1 if none."""
    tree = STRtree(lines)
    pts = crashes.geometry.values
    q, t = tree.query_nearest(pts, max_distance=MATCH_M, all_matches=False)
    out = np.full(len(pts), -1, dtype=int)
    out[q] = t
    return out


def decay_weights(first: int, last: int, halflife: float = HALFLIFE) -> np.ndarray:
    years = np.arange(first, last + 1)
    return 0.5 ** ((last - years) / halflife)


def exposure(attrs: pd.DataFrame, first: int, last: int, halflife: float = HALFLIFE) -> np.ndarray:
    """Recency-weighted exposure per segment in units of 100 million vehicle-miles."""
    per_year = attrs.adt.to_numpy() * attrs.miles.to_numpy() * 365.0 / 1e8
    return per_year * decay_weights(first, last, halflife).sum()


def observed(crash_weight: np.ndarray, seg_idx: np.ndarray, n: int) -> np.ndarray:
    ok = seg_idx >= 0
    return np.bincount(seg_idx[ok], weights=crash_weight[ok], minlength=n)


def eb_rates(obs: np.ndarray, expo: np.ndarray, klass: np.ndarray, m: float) -> tuple[np.ndarray, dict]:
    """Empirical-Bayes rate per segment (crashes per 100M vehicle-miles) and the pooled class rates."""
    prior = {}
    prior_per_seg = np.zeros(len(obs))
    for f in np.unique(klass):
        sel = klass == f
        prior[int(f)] = float(obs[sel].sum() / expo[sel].sum())
        prior_per_seg[sel] = prior[int(f)]
    if m >= 1e8:
        return prior_per_seg, prior
    return (obs + m * prior_per_seg) / (expo + m), prior


def crash_frame(until: int, since: int = FIRST_YEAR):
    """Geocoded crashes for years since..until (UTM points) with severity weights."""
    c = b.load_crashes(b.CSV_PATH, until=until, halflife=None)
    return c[c["date"].dt.year >= since].reset_index(drop=True)


def profile_multiplier(c, profile: str) -> np.ndarray:
    mult = b.load_profile_multipliers().get(profile)
    if not mult:
        return np.ones(len(c))
    return c["ctype"].map(mult).fillna(1.0).to_numpy()


def build(until: int, m: float, halflife: float = HALFLIFE) -> dict:
    attrs, lines = load_segments()
    c = crash_frame(until)
    seg_idx = match_crashes(lines, c)
    years = c["date"].dt.year.to_numpy()
    base = c["weight"].to_numpy() * 0.5 ** ((until - years) / halflife)
    expo = exposure(attrs, FIRST_YEAR, until, halflife)
    klass = attrs.F.to_numpy()
    out = {}
    for name, profile in (("rate", None), ("teen", "teen"), ("elderly", "elderly")):
        w = base * (profile_multiplier(c, profile) if profile else 1.0)
        obs = observed(w, seg_idx, len(attrs))
        out[name], prior = eb_rates(obs, expo, klass, m)
        if name == "rate":
            class_rates = prior
    return {"meta": {"until": until, "first_year": FIRST_YEAR, "halflife": halflife, "prior_m": m, "match_m": MATCH_M,
                     "segments": len(attrs), "crashes_matched": int((seg_idx >= 0).sum()), "crashes": int(len(c)),
                     "class_rate_per_100M_vmt": {k: round(v, 2) for k, v in class_rates.items()},
                     "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            **{k: [round(float(x), 2) for x in v] for k, v in out.items()}}


# ---------------------------------------------------------------- validation

def validate(until: int) -> dict:
    """Held-out check: train on years <= until-2, predict crash COUNTS for until-1..until on every segment."""
    attrs, lines = load_segments()
    split = until - 2
    c = crash_frame(until)
    seg_idx = match_crashes(lines, c)
    years = c["date"].dt.year.to_numpy()
    train, test = years <= split, years > split
    n = len(attrs)
    klass = attrs.F.to_numpy()
    # counts only (no severity or recency weights): the Poisson likelihood is about how many crashes happen
    obs_tr = observed(train.astype(float), seg_idx, n)
    obs_te = observed(test.astype(float), seg_idx, n)
    expo_tr = exposure(attrs, FIRST_YEAR, split, halflife=1e9)           # equal weights over the training years
    expo_te = attrs.adt.to_numpy() * attrs.miles.to_numpy() * 365.0 / 1e8 * (until - split)
    rows = []
    for m in M_GRID:
        rate, _ = eb_rates(obs_tr, expo_tr, klass, m)
        mu = np.maximum(rate * expo_te, 1e-12)
        ll = float((obs_te * np.log(mu) - mu).sum())
        rows.append({"m": m, "loglik": ll})
    base = next(r for r in rows if r["m"] >= 1e8)["loglik"]               # class-average only
    for r in rows:
        r["gain_over_class_avg"] = r["loglik"] - base
    best = max(rows, key=lambda r: r["loglik"])
    return {"split_year": split, "train_crashes": int(obs_tr.sum()), "test_crashes": int(obs_te.sum()), "rows": rows,
            "best_m": best["m"], "segments": n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=int, default=date.today().year - 1, help="last complete crash year to use")
    ap.add_argument("--m", type=float, default=None, help="smoothing strength; default = value tuned by --validate / PRIOR_M")
    ap.add_argument("--out", type=Path, default=RATES_PATH)
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    m = PRIOR_M if args.m is None else args.m
    if args.validate:
        v = validate(args.until)
        print(f"held-out check: train through {v['split_year']} ({v['train_crashes']:,} crashes), "
              f"test {v['split_year'] + 1}-{args.until} ({v['test_crashes']:,} crashes) over {v['segments']:,} segments")
        print(f"{'smoothing M':>12s} {'held-out log-lik':>18s} {'gain vs class average':>22s}")
        for r in v["rows"]:
            label = "class avg" if r["m"] >= 1e8 else ("raw (none)" if r["m"] == 0 else f"{r['m']:g}")
            print(f"{label:>12s} {r['loglik']:18.1f} {r['gain_over_class_avg']:22.1f}")
        print(f"best M = {v['best_m']:g}")
        if args.m is None:
            m = v["best_m"] if 0 < v["best_m"] < 1e8 else PRIOR_M
    data = build(args.until, m)
    args.out.write_text(json.dumps(data, separators=(",", ":")))
    mt = data["meta"]
    print(f"wrote {args.out}: {mt['segments']:,} segments, {mt['crashes_matched']:,} of {mt['crashes']:,} crashes matched, M={m:g}")
    print("class rates (severity-weighted crashes per 100M vehicle-miles):", mt["class_rate_per_100M_vmt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
