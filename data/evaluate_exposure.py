"""Grid model vs exposure model on the 200 cached trips, judged per VEHICLE on crashes neither model saw.

    python evaluate_exposure.py

Both models are built only from crashes through 2023. Each candidate route is then given a REALIZED
per-vehicle risk from crashes in 2024-2025: for every route sample that matches a TxDOT segment, the segment's
realized rate (held-out severity-weighted crashes / held-out vehicle-miles) times the distance; samples that
match no segment (mostly local streets, which have no traffic counts) get the pooled realized rate of major
collectors, the same for both models. Lower is safer per vehicle.

Also reported: the old "crashes along the route" count, which rewards avoiding busy roads whether or not they
are riskier per car, so it is shown only to explain why the two models disagree.
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

import app as A
import build_exposure as be
import build_risk as b
import evaluate as ev
import scoring

HERE = Path(__file__).parent
OUT = HERE / "eval" / "EXPOSURE_COMPARISON.md"
HELD_FIRST, HELD_LAST = ev.HELD_FIRST, ev.HELD_LAST
rng = np.random.default_rng(ev.SEED)


def setup() -> None:
    ev.use_train_grid()                                              # grid and segment rates through 2023


def run_model(model: str, trips, held, realized) -> pd.DataFrame:
    os.environ["RISK_MODEL"] = model
    rows = []
    for t in trips:
        cands = t["candidates"]
        for c in cands:
            c.setdefault("held", held.along(c["coords"]))
            if "pv" not in c:
                c["pv"] = realized.of(c["coords"], c.get("road_classes"))
        for prof in ev.PROFILES:
            for c in cands:
                c["score"], _ = scoring.score_route(c["coords"], prof, c["instructions"], road_classes=c.get("road_classes"),
                                                    road_environment=c.get("environments"))
            rules = A.ROUTING_RULES[prof]
            fast = min(cands, key=lambda c: c["minutes"])
            ours = A._pick_safest(cands, fast, 1.0, rules)
            cap = [c for c in cands if c["minutes"] <= fast["minutes"] * rules["max_detour"]]
            best = min(cap, key=lambda c: c["pv"])                    # headroom: best realized per-vehicle route within the cap
            rows.append({"model": model, "trip": t["id"], "bucket": t["bucket"], "profile": prof, "same": ours is fast,
                         "fast_min": fast["minutes"], "ours_min": ours["minutes"], "best_min": best["minutes"],
                         "fast_pv": fast["pv"], "ours_pv": ours["pv"], "best_pv": best["pv"],
                         "fast_held": fast["held"]["weighted"], "ours_held": ours["held"]["weighted"],
                         "fast_model": fast["score"], "ours_model": ours["score"]})
    return pd.DataFrame(rows)


def ci(x):
    idx = rng.integers(0, len(x), size=(4000, len(x)))
    m = x[idx].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def summarize(df: pd.DataFrame, n_held: int, local: float) -> str:
    L = []
    w = L.append
    w(f"# Grid model vs exposure model ({df.trip.nunique()} trips x {df.profile.nunique()} profiles)\n")
    w(f"Both built from crashes through {ev.TRAIN_UNTIL}. Judged per vehicle on {n_held:,} crashes from {HELD_FIRST}-{HELD_LAST}: "
      f"each route's realized crash rate per vehicle-mile (TxDOT traffic counts) summed over its length; stretches with no "
      f"TxDOT segment use the pooled realized rate of major collectors ({local:.0f} per 100M vehicle-miles). Lower is safer.\n")
    w("| model | profile | reroutes | minutes added | realized per-vehicle risk vs fastest | 95% CI of mean change | changed trips safer / worse | crashes counted along route |")
    w("|---|---|---|---|---|---|---|---|")
    for model in ("grid", "exposure"):
        for prof in ev.PROFILES:
            d = df[(df.model == model) & (df.profile == prof)]
            dpv = (d.ours_pv - d.fast_pv).to_numpy()
            lo, hi = ci(dpv)
            ch = d[~d.same]
            wins, loss = int((ch.ours_pv < ch.fast_pv).sum()), int((ch.ours_pv > ch.fast_pv).sum())
            w(f"| {model} | {prof} | {100 * (~d.same).mean():.0f}% | {(d.ours_min - d.fast_min).mean():+.2f} | "
              f"**{100 * dpv.sum() / d.fast_pv.sum():+.1f}%** | {lo:+.1f} to {hi:+.1f} | {wins} / {loss} | "
              f"{100 * (d.ours_held.sum() - d.fast_held.sum()) / d.fast_held.sum():+.1f}% |")
    w("")
    w("Headroom (best realized per-vehicle route within each profile's detour cap, an upper bound nobody can pick in advance): "
      + ", ".join(f"{p} {100 * (d.best_pv.sum() - d.fast_pv.sum()) / d.fast_pv.sum():+.1f}% for {(d.best_min - d.fast_min).mean():+.2f} min"
                  for p, d in df[df.model == 'exposure'].groupby('profile')))
    return "\n".join(L)


def main() -> None:
    setup()
    trips = ev.load_cached_trips()
    held, realized = ev.HeldOut(), ev.RealizedRisk()
    print(f"{len(trips)} trips; realized per-vehicle rates from {realized.crashes:,} crashes {HELD_FIRST}-{HELD_LAST}")
    df = pd.concat([run_model(m, trips, held, realized) for m in ("grid", "exposure")], ignore_index=True)
    text = summarize(df, held.n, realized.local)
    df.to_csv(HERE / "eval" / "exposure_comparison.csv", index=False, float_format="%.4f")
    OUT.write_text(text + "\n")
    print("\n" + text)


if __name__ == "__main__":
    main()
