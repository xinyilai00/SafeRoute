"""Does the router pick routes that are actually safer, without costing much time?

    python evaluate.py                  # 200 trips x 3 profiles, real GraphHopper + TomTom
    python evaluate.py --trips 20       # quick run
    python evaluate.py --analyze-only   # re-analyze cached routes without calling any API
    python evaluate.py --analyze-only --half tune   # tune settings on the even-numbered trips
    python evaluate.py --analyze-only --half test   # report final settings on the odd-numbered trips, once

Test design
-----------
* Trips: random start/end points drawn from real crash locations (so they sit on real roads), in three
  length groups (short 2-6 km, medium 6-15 km, long 15-25 km), fixed seed.
* Routes: the full pipeline (GraphHopper alternatives, closure blocking, TomTom live times). Candidates
  are fetched once per trip and scored for each profile, since they don't depend on the profile.
* The scoring grid is built ONLY from crashes through 2023 (TRAIN_UNTIL). "Safer" is then judged with an
  INDEPENDENT measure: crashes from 2024 onward that the model never saw, counted within BUFFER_M of each
  route. Judging with the model's own risk score would be circular, so that is reported only for reference.
* Compared per trip and profile: fastest route vs the chosen safest route, plus two baselines:
    - "typical alternative": the average over the other candidates within the detour cap (is our pick
      better than just taking some other route?)
    - "min-risk": the route with the lowest model risk within the cap, ignoring time (does the time-aware
      rule give up much safety, and does it save time?)

Caveats (also written into the report): crashes near a route are a measure of exposure, not risk per car;
busy roads have more crashes. Trip endpoints come from crash locations, which over-represent busy
corridors. This is one city and about 2.8 years of held-out crashes.
"""
import argparse
import csv
import gzip
import json
import math
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import STRtree
from shapely.geometry import LineString

import app as A  # loads .env (GraphHopper URL, TomTom key)
import build_risk as b
import live
import routing
import scoring

HERE = Path(__file__).parent
RAW = HERE / "raw" / "eval"
OUT = HERE / "eval"
TRIPS_GZ = OUT / "trips.json.gz"  # compact copy of the fetched routes, committed so CI can re-score them
TRAIN_UNTIL = 2023
BUFFER_M = 30.0
PROFILES = ("teen", "elderly", "sensitive_passenger")
BUCKETS = (("short", 2.0, 6.0, 70), ("medium", 6.0, 15.0, 80), ("long", 15.0, 25.0, 50))  # quotas sum to 200
SEED = 42
BOOT = 4000


# ---------------------------------------------------------------- setup

def build_train_grid(path: Path) -> None:
    """Risk grid from crashes through TRAIN_UNTIL only, in the same format as risk.geojson."""
    crashes = b.load_crashes(b.CSV_PATH, until=TRAIN_UNTIL, halflife=5.0)
    grid = b.build_grid(crashes).to_crs("EPSG:4326")
    grid["weighted"] = grid["weighted"].round(1)
    grid["left_weighted"] = grid["left_weighted"].round(1)
    gj = json.loads(grid.to_json(drop_id=True, na="null", to_wgs84=True))
    gj["grid"] = {"cell_m": b.CELL_M, "crs": b.UTM}
    path.write_text(json.dumps(gj, separators=(",", ":")))


def use_train_grid() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"grid_through_{TRAIN_UNTIL}.geojson"
    if not path.exists():
        build_train_grid(path)
    scoring.RISK_PATH = path
    scoring._grid.cache_clear()


def sample_points() -> list[tuple[float, float]]:
    g = b.load_crashes(b.CSV_PATH, until=TRAIN_UNTIL)
    return list(zip(g["latitude"], g["longitude"]))


def dist_km(a, c) -> float:
    return routing._haversine_m([a[1], a[0]], [c[1], c[0]]) / 1000.0


def fetch_trips(n: int, seed: int, cache: Path) -> list[dict]:
    """Trips with their candidate routes (cached on disk; GraphHopper + TomTom are only called once)."""
    done = json.loads(cache.read_text()) if cache.exists() else []
    scale = n / sum(q for *_, q in BUCKETS)
    quotas = {name: max(1, round(q * scale)) for name, _, _, q in BUCKETS}
    have = {name: sum(1 for t in done if t["bucket"] == name) for name in quotas}
    if all(have[k] >= quotas[k] for k in quotas):
        return done
    pts = sample_points()
    rng = random.Random(seed + len(done))
    prov = routing.get_provider()
    if prov.name == "fake":
        raise SystemExit("GH_URL is not set; evaluation needs the real routing engine")
    blocked = live.closure_area() if live.enabled() else None
    t0 = time.time()
    for name, lo, hi, _ in BUCKETS:
        tries = 0
        while have[name] < quotas[name] and tries < quotas[name] * 12:
            tries += 1
            o, d = rng.choice(pts), rng.choice(pts)
            if not lo <= dist_km(o, d) < hi:
                continue
            oo, dd = {"lat": o[0], "lng": o[1]}, {"lat": d[0], "lng": d[1]}
            try:
                try:
                    cands = prov.routes(oo, dd, blocked=blocked)
                except Exception:
                    cands = prov.routes(oo, dd)  # an endpoint inside a closure: route normally
            except Exception:
                continue  # GraphHopper could not snap or route this pair
            if len(cands) < 1:
                continue
            info = live.apply_live(cands) if live.enabled() else {"live": False, "dropped": 0}
            done.append({"id": len(done), "bucket": name, "origin": oo, "destination": dd,
                         "live": bool(info["live"]), "dropped": info["dropped"],
                         "candidates": [{k: c.get(k) for k in ("coords", "minutes", "free_minutes", "miles",
                                                               "instructions", "road_classes", "environments")}
                                        for c in cands]})
            have[name] += 1
            cache.write_text(json.dumps(done))
            if len(done) % 10 == 0:
                print(f"  {len(done)} trips fetched ({time.time() - t0:.0f}s)")
    return done


# ---------------------------------------------------------------- held-out crashes

class HeldOut:
    """Crashes from 2024 on (not used to build the scoring grid), counted along routes."""

    def __init__(self):
        g = b.load_crashes(b.CSV_PATH, since=TRAIN_UNTIL + 1)
        self.tree = STRtree(g.geometry.values)
        self.weight = g["weight"].to_numpy()
        self.ksi = g["crash_sev_id"].isin([1, 4]).to_numpy()
        self.n = len(g)
        self.to_utm = scoring._to_utm()

    def along(self, coords) -> dict:
        xs, ys = self.to_utm.transform([c[0] for c in coords], [c[1] for c in coords])
        line = LineString(list(zip(xs, ys)))
        idx = self.tree.query(line.buffer(BUFFER_M), predicate="intersects")
        return {"crashes": int(len(idx)), "weighted": float(self.weight[idx].sum()),
                "ksi": int(self.ksi[idx].sum()), "km": line.length / 1000.0}


# ---------------------------------------------------------------- evaluation

cand_rows: list[dict] = []  # per candidate route, for the score-validity check

def evaluate(trips: list[dict], held: HeldOut) -> pd.DataFrame:
    rows = []
    cand_rows.clear()
    for t in trips:
        cands = t["candidates"]
        for c in cands:
            c["held"] = held.along(c["coords"])
        for prof in PROFILES:
            for c in cands:
                c["score"], _ = scoring.score_route(c["coords"], prof, c["instructions"],
                                                    road_classes=c.get("road_classes"),
                                                    road_environment=c.get("environments"))
            if prof == PROFILES[0]:
                for i, c in enumerate(cands):
                    cand_rows.append({"trip": t["id"], "cand": i, "model": c["score"], "held": c["held"]["weighted"],
                                      "km": c["held"]["km"], "minutes": c["minutes"]})
            rules = A.ROUTING_RULES[prof]
            fast = min(cands, key=lambda c: c["minutes"])
            ours = A._pick_safest(cands, fast, 1.0, rules)
            minrisk = A._pick_safest(cands, fast, 1.0, {**rules, "beta": 1e6})
            within = [c for c in cands if c is not fast and c["minutes"] <= fast["minutes"] * rules["max_detour"]]

            def pack(prefix, r):
                return {f"{prefix}_min": r["minutes"], f"{prefix}_km": r["held"]["km"], f"{prefix}_model": r["score"],
                        f"{prefix}_held": r["held"]["weighted"], f"{prefix}_held_n": r["held"]["crashes"],
                        f"{prefix}_held_ksi": r["held"]["ksi"]}
            row = {"trip": t["id"], "bucket": t["bucket"], "profile": prof, "live": t["live"],
                   "candidates": len(cands), "same": ours is fast, "minrisk_same": minrisk is fast,
                   **pack("fast", fast), **pack("ours", ours), **pack("minrisk", minrisk)}
            for k in ("min", "model", "held", "held_n", "held_ksi"):
                src = {"min": "minutes", "model": "score"}.get(k)
                vals = [(c[src] if src else c["held"][{"held": "weighted", "held_n": "crashes", "held_ksi": "ksi"}[k]]) for c in within]
                row[f"alt_{k}"] = float(np.mean(vals)) if vals else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def boot_ci(x: np.ndarray, rng) -> tuple[float, float]:
    idx = rng.integers(0, len(x), size=(BOOT, len(x)))
    m = x[idx].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return float("nan")
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def validity(cd: pd.DataFrame):
    """(per-trip rank correlations, concordant pairs, tied pairs, comparable pairs) between a candidate's
    model score and its held-out crashes, over trips with 3+ candidates."""
    rhos, agree, ties, pairs = [], 0, 0, 0
    for _, g in cd.groupby("trip"):
        if len(g) < 3:
            continue
        if g.model.nunique() > 1 and g.held.nunique() > 1:
            rhos.append(g.model.rank().corr(g.held.rank()))
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, c = g.iloc[i], g.iloc[j]
                if a.model == c.model or a.held == c.held:
                    ties += 1
                    continue
                pairs += 1
                agree += (a.model < c.model) == (a.held < c.held)
    return rhos, agree, ties, pairs


def compute_metrics(df: pd.DataFrame, held_n: int) -> dict:
    """Headline numbers as plain JSON; refresh.py compares these with the previous run."""
    rhos, agree, ties, pairs = validity(pd.DataFrame(cand_rows))
    out = {"trips": int(df.trip.nunique()), "cases": int(len(df)), "held_out_crashes": int(held_n),
           "pair_concordance": round(agree / pairs, 4) if pairs else None,
           "rank_corr": round(float(np.mean(rhos)), 4) if rhos else None, "profiles": {}}
    for prof, d in df.groupby("profile"):
        out["profiles"][prof] = {
            "changed_share": round(float((~d.same).mean()), 4),
            "minutes_added": round(float((d.ours_min - d.fast_min).mean()), 4),
            "held_change_pct": round(100 * float((d.ours_held.sum() - d.fast_held.sum()) / d.fast_held.sum()), 3),
            "ksi_change_pct": round(100 * float((d.ours_held_ksi.sum() - d.fast_held_ksi.sum()) / max(d.fast_held_ksi.sum(), 1)), 3)}
    return out


def load_cached_trips():
    """Fetched routes: the local raw cache if present, else the committed gzip copy, else None."""
    cache = RAW / "trips.json"
    if cache.exists():
        return json.loads(cache.read_text())
    if TRIPS_GZ.exists():
        with gzip.open(TRIPS_GZ, "rt") as f:
            return json.load(f)
    return None


def summarize(df: pd.DataFrame, held_n: int) -> str:
    rng = np.random.default_rng(SEED)
    L = []
    w = L.append
    for prof in PROFILES:
        d = df[df.profile == prof]
        n, nd = len(d), int((~d.same).sum())
        dt = (d.ours_min - d.fast_min).to_numpy()
        dh = (d.ours_held - d.fast_held).to_numpy()
        dm = (d.ours_model - d.fast_model).to_numpy()
        diff = d[~d.same]
        wins = int((diff.ours_held < diff.fast_held).sum())
        losses = int((diff.ours_held > diff.fast_held).sum())
        lo, hi = boot_ci(dh, rng)
        tlo, thi = boot_ci(dt, rng)
        w(f"### {prof}  ({n} trips)")
        w(f"- Safest differs from fastest on **{nd} trips ({nd / n:.0%})**; the other {n - nd} get the fastest route.")
        w(f"- Time added, all trips: mean **{dt.mean():+.2f} min** (95% CI {tlo:+.2f} to {thi:+.2f}), "
          f"i.e. {100 * dt.sum() / d.fast_min.sum():+.1f}% of total fastest time. "
          f"On the {nd} changed trips: mean {diff.ours_min.sub(diff.fast_min).mean():+.1f} min, "
          f"median {diff.ours_min.sub(diff.fast_min).median():+.1f} min.")
        w(f"- **Held-out crashes along the route** (2024+, severity-weighted): fastest {d.fast_held.mean():.1f} -> safest "
          f"{d.ours_held.mean():.1f}  (mean change **{dh.mean():+.2f}**, 95% CI {lo:+.2f} to {hi:+.2f}; "
          f"{100 * dh.sum() / d.fast_held.sum():+.1f}% overall).")
        w(f"  - On changed trips the safest had fewer held-out crashes on **{wins}** and more on **{losses}** "
          f"(sign test p = {sign_test(wins, losses):.3f}).")
        w(f"  - Serious/fatal held-out crashes: {d.fast_held_ksi.mean():.2f} -> {d.ours_held_ksi.mean():.2f} per trip "
          f"({100 * (d.ours_held_ksi.sum() - d.fast_held_ksi.sum()) / max(d.fast_held_ksi.sum(), 1):+.1f}%).")
        w(f"- Model risk score (circular, reference only): {100 * dm.sum() / d.fast_model.sum():+.1f}%.")
        alt = d.dropna(subset=["alt_held"])
        if len(alt):
            w(f"- Baseline, a typical other route within the cap ({len(alt)} trips with alternatives): "
              f"{100 * (alt.alt_held.sum() - alt.fast_held.sum()) / alt.fast_held.sum():+.1f}% held-out crashes and "
              f"{(alt.alt_min - alt.fast_min).mean():+.1f} min vs the fastest. Our pick: "
              f"{100 * (alt.ours_held.sum() - alt.fast_held.sum()) / alt.fast_held.sum():+.1f}% and "
              f"{(alt.ours_min - alt.fast_min).mean():+.1f} min on the same trips.")
        w(f"- Baseline, minimize model risk ignoring time: {int((~d.minrisk_same).sum())} changed trips, "
          f"{(d.minrisk_min - d.fast_min).mean():+.2f} min and {100 * (d.minrisk_held.sum() - d.fast_held.sum()) / d.fast_held.sum():+.1f}% "
          f"held-out crashes (ours: {dt.mean():+.2f} min, {100 * dh.sum() / d.fast_held.sum():+.1f}%).")
        w("")
    w("### Does the route-level model score predict later crashes? (independent check)")
    rhos, agree, ties, pairs = validity(pd.DataFrame(cand_rows))
    if rhos:
        lo, hi = boot_ci(np.array(rhos), rng)
        w(f"- Within a trip, rank correlation between a candidate's model score and its held-out crashes: mean **{np.mean(rhos):.2f}** "
          f"(95% CI {lo:.2f} to {hi:.2f}, {len(rhos)} trips with 3+ routes).")
    if pairs:
        w(f"- For pairs of candidate routes for the same trip, the lower model score also had fewer held-out crashes in "
          f"**{agree}/{pairs} = {agree / pairs:.0%}** of pairs ({ties} tied pairs ignored; 50% would be chance).")
    w("")
    w("### Crashes per km (is the safest route just longer or shorter?)")
    for prof in PROFILES[:1]:
        d = df[df.profile == prof]
        w(f"- Held-out crashes per km along the route: fastest {d.fast_held.sum() / d.fast_km.sum():.2f} -> safest "
          f"{d.ours_held.sum() / d.ours_km.sum():.2f} (route length {d.fast_km.mean():.1f} -> {d.ours_km.mean():.1f} km on average).")
    w("")
    w("### By trip length (all profiles pooled)")
    for bucket in (b_[0] for b_ in BUCKETS):
        d = df[df.bucket == bucket]
        w(f"- {bucket}: {len(d)} cases, changed {100 * (~d.same).mean():.0f}%, time {(d.ours_min - d.fast_min).mean():+.2f} min, "
          f"held-out crashes {100 * (d.ours_held.sum() - d.fast_held.sum()) / d.fast_held.sum():+.1f}%")
    w("")
    w(f"Live TomTom times were available for {100 * df.groupby('trip').live.first().mean():.0f}% of trips "
      f"(the rest use GraphHopper free-flow times). Held-out crashes: {held_n:,} (2024 to latest).")
    return "\n".join(L)


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trips", type=int, default=200)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--half", choices=("tune", "test"),
                    help="score only even (tune) or odd (test) trip ids, so settings tuned on one half "
                         "are reported on trips they were not tuned on")
    args = ap.parse_args()

    use_train_grid()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)
    cache = RAW / "trips.json"
    if args.analyze_only:
        trips = load_cached_trips()
        if trips is None:
            raise SystemExit("no cached routes: run once without --analyze-only (needs GraphHopper)")
    else:
        print("fetching routes (GraphHopper + TomTom) ...")
        trips = fetch_trips(args.trips, args.seed, cache)
        with gzip.open(TRIPS_GZ, "wt") as f:
            json.dump(trips, f, separators=(",", ":"))
    if args.half:
        trips = [t for t in trips if t["id"] % 2 == (0 if args.half == "tune" else 1)]
    print(f"{len(trips)} trips; scoring with the grid built from crashes through {TRAIN_UNTIL}")
    held = HeldOut()
    df = evaluate(trips, held)
    df.to_csv(OUT / "results.csv", index=False, float_format="%.4f")
    (OUT / "metrics.json").write_text(json.dumps(compute_metrics(df, held.n), indent=2))
    text = summarize(df, held.n)
    header = (f"# Router evaluation ({len(trips)} trips x {len(PROFILES)} profiles = {len(df)} cases)\n\n"
              f"Grid built from crashes through {TRAIN_UNTIL}; \"safer\" judged by held-out crashes from "
              f"{TRAIN_UNTIL + 1} on within {BUFFER_M:.0f} m of the route. Seed {args.seed}."
              + (f" {args.half.capitalize()} half only." if args.half else "") + "\n\n")
    (OUT / "REPORT.md").write_text(header + text + "\n")
    print("\n" + header + text)
    print(f"\nwrote {OUT / 'results.csv'} and {OUT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
