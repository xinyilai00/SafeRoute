"""Self-updating pipeline: pull fresh data, rebuild everything, validate, then keep or roll back.

    python refresh.py                  # full run: download, rebuild, check, keep or roll back
    python refresh.py --ci             # same, plus GitHub Actions outputs; exit code 1 if rejected
    python refresh.py --skip-download  # rebuild from the files already in raw/ (fast, for testing)
    python refresh.py --dry-run        # run every check, then restore the old files and write nothing

What it does
1. Remember the current grid (risk.geojson) and crash list, then download new crashes (and the signal and
   pavement data), and rebuild the profile ratios, the grid and, when a new year has completed, the weather
   effect.
2. FORWARD CHECK: crashes that arrived since the last build are genuinely new to the old grid. How well did
   the old grid rank them (share landing in its top 10% of squares)? Logged to history.json so you can see
   drift over time. A warning only: a change in the world isn't a reason to reject a rebuild.
3. GATE: the rebuilt data is only accepted if
     - structure is sane (no blanks, risk in 0..1, required layers, similar number of squares),
     - it is still similar to the previous grid (correlation >= SIMILARITY_MIN),
     - a rolling backtest (train through two years ago, test on the rest) captures enough crashes and has
       not dropped much since the last accepted run,
     - the 200-trip route evaluation (cached routes re-scored offline, no GraphHopper or TomTom needed) still
       shows the safest route is meaningfully safer, and the route score still predicts later crashes,
     - the unit tests pass.
4. Accepted: new files stay, history.json and eval/REFRESH_REPORT.md are updated (the GitHub workflow then
   opens a pull request for a human to merge). Rejected: every file is restored and the reasons are logged.

The pass/fail logic is deliberately plain numbers, never a language model.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
HISTORY = HERE / "history.json"
REPORT = HERE / "eval" / "REFRESH_REPORT.md"
BACKUP = HERE / "raw" / "refresh_backup"
GRID = HERE / "risk.geojson"
# everything the pipeline writes and tracks in git; restored together on rejection
ARTIFACTS = ["risk.geojson", "profile_ratios.json", "signals.json", "street_condition.json", "weather_effect.json",
             "eval/results.csv", "eval/REPORT.md", "eval/metrics.json"]

# ---- gate thresholds (see the module docstring) ----
CELL_RATIO_RANGE = (0.85, 1.30)    # new square count / previous square count
SIMILARITY_MIN = 0.95              # Pearson correlation of risk over squares in both grids
BACKTEST_FLOOR = 0.50              # share of later crashes in the top 10% of squares (currently ~0.58)
BACKTEST_MAX_DROP = 0.03           # vs the last accepted run
ROUTE_HELD_MAX = -2.0              # safest route must cut held-out crashes by at least this % (currently ~-5%)
ROUTE_MAX_REGRESS = 2.0            # percentage points worse than the last accepted run
CONCORDANCE_MIN = 0.55             # route-pair agreement between model score and later crashes (chance = 0.5)
DRIFT_WARN_UPPER = 0.40            # warn if even the optimistic end of the forward capture is below this
REQUIRED_PROPS = ("ix", "iy", "risk", "left_risk", "risk_teen", "risk_elderly")


# ---------------------------------------------------------------- pure checks (unit tested)

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k successes out of n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def cell_risk(gj: dict) -> dict:
    return {(f["properties"]["ix"], f["properties"]["iy"]): f["properties"]["risk"] for f in gj["features"]}


def check_structure(new: dict, prev: dict | None) -> list[str]:
    """Reasons the new grid is unusable (empty list = fine)."""
    problems = []
    feats = new.get("features") or []
    if not feats:
        return ["grid has no squares"]
    for key in REQUIRED_PROPS:
        if any(key not in f["properties"] or f["properties"][key] is None for f in feats):
            problems.append(f"property '{key}' missing or null on some squares")
    risks = np.array([f["properties"].get("risk", np.nan) for f in feats], dtype=float)
    if np.isnan(risks).any() or risks.min() < 0 or risks.max() > 1:
        problems.append("risk values outside 0..1 or missing")
    elif risks.max() < 0.999:
        problems.append("top square is not normalised to 1.0")
    keys = [(f["properties"]["ix"], f["properties"]["iy"]) for f in feats if "ix" in f["properties"]]
    if len(keys) != len(set(keys)):
        problems.append("duplicate squares")
    if prev:
        ratio = len(feats) / max(len(prev["features"]), 1)
        if not CELL_RATIO_RANGE[0] <= ratio <= CELL_RATIO_RANGE[1]:
            problems.append(f"square count changed by {ratio:.2f}x (allowed {CELL_RATIO_RANGE[0]}-{CELL_RATIO_RANGE[1]}x)")
    return problems


def similarity(new: dict, prev: dict) -> float | None:
    """Pearson correlation of risk over squares present in both grids."""
    a, b = cell_risk(new), cell_risk(prev)
    common = sorted(set(a) & set(b))
    if len(common) < 100:
        return None
    x = np.array([a[k] for k in common])
    y = np.array([b[k] for k in common])
    return float(np.corrcoef(x, y)[0, 1])


def forward_capture(prev: dict, new_cells: list, top: float = 0.10) -> dict:
    """How well the previous grid ranked crashes that arrived after it was built.

    new_cells: one (ix, iy) per new crash. Returns the share landing in the previous grid's top `top`
    squares, with a Wilson 95% interval. Chance level is `top`.
    """
    risk = cell_risk(prev)
    k = max(int(len(risk) * top), 1)
    top_cells = set(sorted(risk, key=risk.get, reverse=True)[:k])
    hits = sum(1 for c in new_cells if c in top_cells)
    n = len(new_cells)
    lo, hi = wilson(hits, n)
    return {"n": n, "hits": hits, "capture": (hits / n) if n else None, "ci": [round(lo, 4), round(hi, 4)]}


def decide(checks: dict, last: dict | None) -> tuple[bool, list[str], list[str]]:
    """Gate logic. `checks` holds the measured values; `last` is the previous accepted history entry.

    Returns (accepted, failure reasons, warnings).
    """
    fails, warns = [], []
    fails += checks.get("structure", [])
    if checks.get("similarity") is not None and checks["similarity"] < SIMILARITY_MIN:
        fails.append(f"new grid differs too much from the previous one (correlation {checks['similarity']:.3f} < {SIMILARITY_MIN})")
    bt = checks.get("backtest")
    if bt is not None:
        if bt < BACKTEST_FLOOR:
            fails.append(f"backtest capture {bt:.3f} below the floor {BACKTEST_FLOOR}")
        prev_bt = (last or {}).get("backtest")
        if prev_bt is not None and bt < prev_bt - BACKTEST_MAX_DROP:
            fails.append(f"backtest capture fell {prev_bt:.3f} -> {bt:.3f} (more than {BACKTEST_MAX_DROP})")
    route = checks.get("route")
    if route:
        prev_route = (last or {}).get("route") or {}
        for prof, m in route["profiles"].items():
            if m["held_change_pct"] > ROUTE_HELD_MAX:
                fails.append(f"{prof}: safest route no longer meaningfully safer ({m['held_change_pct']:+.1f}% held-out crashes, need <= {ROUTE_HELD_MAX}%)")
            was = (prev_route.get("profiles") or {}).get(prof)
            if was and m["held_change_pct"] > was["held_change_pct"] + ROUTE_MAX_REGRESS:
                fails.append(f"{prof}: route benefit regressed {was['held_change_pct']:+.1f}% -> {m['held_change_pct']:+.1f}%")
        conc = route.get("pair_concordance")
        if conc is not None and conc < CONCORDANCE_MIN:
            fails.append(f"route score no longer predicts later crashes (pair agreement {conc:.2f} < {CONCORDANCE_MIN})")
    if checks.get("tests_ok") is False:
        fails.append("unit tests failed")
    fwd = checks.get("forward")
    if fwd and fwd.get("capture") is not None and fwd["ci"][1] < DRIFT_WARN_UPPER:
        warns.append(f"drift: the previous grid ranked the {fwd['n']} newest crashes poorly "
                     f"({fwd['capture']:.0%} in its top 10%, 95% interval {fwd['ci'][0]:.0%}-{fwd['ci'][1]:.0%})")
    return (not fails), fails, warns


def append_history(history: list, entry: dict, keep: int = 200) -> list:
    return (history + [entry])[-keep:]


def last_accepted(history: list) -> dict | None:
    for e in reversed(history):
        if e.get("status") == "accepted":
            return e
    return None


# ---------------------------------------------------------------- pipeline steps

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print("  $", " ".join(cmd))
    return subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)


def backup() -> None:
    if BACKUP.exists():
        shutil.rmtree(BACKUP)
    for rel in ARTIFACTS:
        src = HERE / rel
        if src.exists():
            (BACKUP / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, BACKUP / rel)


def restore() -> None:
    for rel in ARTIFACTS:
        src = BACKUP / rel
        if src.exists():
            shutil.copy2(src, HERE / rel)


def download_all() -> None:
    import build_risk as b
    import calibrate_profiles as cp
    prev = b.CSV_PATH.with_name("crashes.prev.csv")  # the crash list that built the CURRENT grid
    if not prev.exists() and b.CSV_PATH.exists():
        shutil.copy2(b.CSV_PATH, prev)  # first run: the file on disk built the committed grid
    print("downloading crashes and victim records ...")
    b.download(b.CSV_PATH)
    cp.fetch_persons(cp.PERSONS_PATH)


def rebuild() -> list[str]:
    """Rebuild every artifact; returns error messages (empty = ok)."""
    errors = []
    import analyze_weather as aw
    steps = [["build_signals.py"], ["build_pavement.py"], ["calibrate_profiles.py"], ["build_risk.py"]]
    if aw.needed():
        steps.append(["analyze_weather.py"])
    for step in steps:
        r = run([sys.executable, *step])
        if r.returncode != 0:
            errors.append(f"{step[0]} failed: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
            break
    return errors


def new_crash_cells(prev_gj: dict) -> tuple[list, str]:
    """(cell of each crash newer than the previous grid, how 'new' was decided)."""
    import backtest as bt
    import build_risk as b
    crashes = b.load_crashes(b.CSV_PATH, halflife=None)
    prev_csv = b.CSV_PATH.with_name("crashes.prev.csv")
    if prev_csv.exists():
        old_ids = set(pd.read_csv(prev_csv, usecols=["id"])["id"].astype(str))
        fresh = crashes[~crashes["id"].astype(str).isin(old_ids)]
        how = "crash ids not present in the previous download"
    else:
        cutoff = (prev_gj.get("meta") or {}).get("data_through")
        if not cutoff:
            return [], "skipped (no previous download and the previous grid has no build date)"
        fresh = crashes[crashes["date"] > pd.Timestamp(cutoff)]
        how = f"crashes dated after the previous grid's data cutoff ({cutoff[:10]})"
    return list(bt._cells(fresh)), how


def rolling_backtest() -> dict:
    """Capture@10% with the grid trained through (latest year - 2), tested on every later crash."""
    import backtest as bt
    import build_risk as b
    allc = b.load_crashes(b.CSV_PATH, halflife=None)
    train_until = int(allc["date"].dt.year.max()) - 2
    grid = b.build_grid(b.load_crashes(b.CSV_PATH, until=train_until, halflife=5.0))
    test = allc[allc["date"].dt.year > train_until].copy()
    test["cell"] = bt._cells(test)
    counts = test.groupby("cell").size()
    cap = bt._capture(bt._series(grid, "risk"), counts, 0.10, len(grid))
    return {"train_until": train_until, "test_crashes": int(len(test)), "capture10": round(float(cap), 4)}


def route_eval() -> dict | None:
    r = run([sys.executable, "evaluate.py", "--analyze-only"])
    if r.returncode != 0:
        print(r.stderr[-500:])
        return None
    return json.loads((HERE / "eval" / "metrics.json").read_text())


def run_tests() -> tuple[bool, str]:
    r = run([sys.executable, "-m", "pytest", "-q", "-x", str(HERE / "tests")])
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
    return r.returncode == 0, last


def _grid_values(path: Path):
    """{(ix, iy): numeric properties} of a grid, ignoring geometry and metadata (map projections differ in the last
    digits between macOS and Linux, which would otherwise make every refresh look like a change)."""
    if not path.exists():
        return None
    out = {}
    for f in json.loads(path.read_text())["features"]:
        p = f["properties"]
        out[(p["ix"], p["iy"])] = tuple((k, round(v, 6)) for k, v in sorted(p.items()) if isinstance(v, (int, float)))
    return out


def artifacts_changed(prev_dir: Path, cur_dir: Path) -> list[str]:
    """Names of the data artifacts whose MEANING changed (empty = nothing real changed).

    Compares cell values, the set of signals, graded pavement segments, profile ratios and the weather
    effect, so cosmetic differences (polygon coordinates, file order, timestamps) don't count.
    """
    changed = []

    def load(d, name):
        p = d / name
        return json.loads(p.read_text()) if p.exists() else None

    if _grid_values(prev_dir / "risk.geojson") != _grid_values(cur_dir / "risk.geojson"):
        changed.append("risk grid")
    a, b = load(prev_dir, "signals.json"), load(cur_dir, "signals.json")
    if a is None or b is None or sorted(map(tuple, a)) != sorted(map(tuple, b)):
        changed.append("signals")
    a, b = load(prev_dir, "street_condition.json"), load(cur_dir, "street_condition.json")
    key = lambda seg: (seg[0], seg[1], tuple(map(tuple, seg[2])))  # noqa: E731
    if a is None or b is None or sorted(map(key, a)) != sorted(map(key, b)):
        changed.append("street condition")
    for name in ("profile_ratios.json", "weather_effect.json"):
        if load(prev_dir, name) != load(cur_dir, name):
            changed.append(name.removesuffix(".json").replace("_", " "))
    return changed


def changed_tracked() -> bool:
    paths = [str(Path("data") / rel) for rel in ARTIFACTS + ["history.json", "eval/REFRESH_REPORT.md"]]
    r = subprocess.run(["git", "status", "--porcelain", "--", *paths], cwd=HERE.parent, capture_output=True, text=True)
    return bool(r.stdout.strip()) if r.returncode == 0 else True


def render_report(entry: dict, fails: list, warns: list) -> str:
    c = entry
    L = [f"# Data refresh {entry['date'][:10]}: **{entry['status'].upper()}**", ""]
    if fails:
        L += ["## Rejected because", *[f"- {f}" for f in fails], ""]
    if warns:
        L += ["## Warnings", *[f"- {w}" for w in warns], ""]
    if c.get("changed"):
        L += ["## What changed", *[f"- {name}" for name in c["changed"]], ""]
    L += ["## Data", f"- Crashes through **{c['data_through'][:10]}**: {c['crashes']:,} geocoded, {c['cells']:,} grid squares."]
    if c.get("new_crashes_note"):
        L.append(f"- New since the last build ({c['new_crashes_note']}): **{c['forward']['n']:,}** crashes.")
    L.append("")
    f = c.get("forward")
    if f and f.get("capture") is not None:
        L += ["## Forward check (the previous grid on crashes it never saw)",
              f"- {f['hits']}/{f['n']} landed in the old grid's top 10% of squares = **{f['capture']:.0%}** "
              f"(95% interval {f['ci'][0]:.0%}-{f['ci'][1]:.0%}; chance is 10%).", ""]
    L += ["## Checks"]
    sim = c.get("similarity")
    L.append(f"- Similarity to previous grid: {'n/a' if sim is None else f'{sim:.4f}'} (need >= {SIMILARITY_MIN})")
    if c.get("backtest") is not None:
        L.append(f"- Rolling backtest (train through {c['backtest_detail']['train_until']}, "
                 f"{c['backtest_detail']['test_crashes']:,} test crashes): top-10% capture **{c['backtest']:.1%}** "
                 f"(floor {BACKTEST_FLOOR:.0%}, chance 10%)")
    r = c.get("route")
    if r:
        L.append(f"- Route evaluation ({r['trips']} cached trips, {r['held_out_crashes']:,} held-out crashes): "
                 f"score/crash pair agreement **{r['pair_concordance']:.0%}**")
        for prof, m in r["profiles"].items():
            L.append(f"  - {prof}: reroutes {m['changed_share']:.0%} of trips, {m['minutes_added']:+.2f} min, "
                     f"held-out crashes **{m['held_change_pct']:+.1f}%**")
    L.append(f"- Unit tests: {c.get('tests', 'not run')}")
    L += ["", "_Pass/fail is decided by fixed numeric thresholds in `data/refresh.py`; see its docstring._"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="record the run even when nothing material changed")
    args = ap.parse_args()

    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    last = last_accepted(history)
    prev_gj = json.loads(GRID.read_text()) if GRID.exists() else None
    backup()

    if not args.skip_download:
        try:
            download_all()
        except Exception as e:  # network trouble: nothing was rebuilt, so nothing to roll back
            print(f"download failed: {e}")
            return finish(args, None, [f"download failed: {e}"], [], history, accepted=False)

    errors = rebuild()
    if errors:
        restore()
        return finish(args, None, errors, [], history, accepted=False)

    new_gj = json.loads(GRID.read_text())
    meta = new_gj.get("meta") or {}
    checks = {"structure": check_structure(new_gj, prev_gj)}
    checks["similarity"] = similarity(new_gj, prev_gj) if prev_gj else None
    entry = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "data_through": meta.get("data_through", ""), "crashes": meta.get("crashes", 0),
             "cells": len(new_gj["features"])}
    if prev_gj:
        cells, how = new_crash_cells(prev_gj)
        entry["forward"] = forward_capture(prev_gj, cells) if cells else {"n": 0, "capture": None, "ci": [0, 1], "hits": 0}
        entry["new_crashes_note"] = how
        checks["forward"] = entry["forward"]
    print("rolling backtest ...")
    bt = rolling_backtest()
    entry["backtest"], entry["backtest_detail"] = bt["capture10"], bt
    checks["backtest"] = bt["capture10"]
    print("route evaluation on cached routes ...")
    entry["route"] = route_eval()
    checks["route"] = entry["route"]
    if entry["route"] is None:
        checks["structure"].append("route evaluation could not run")
    if args.skip_tests:
        entry["tests"], checks["tests_ok"] = "skipped", None
    else:
        ok, summary = run_tests()
        entry["tests"], checks["tests_ok"] = summary, ok
    entry["similarity"] = checks["similarity"]

    accepted, fails, warns = decide(checks, last)
    return finish(args, entry, fails, warns, history, accepted=accepted)


def finish(args, entry, fails, warns, history, accepted: bool) -> int:
    if entry is None:
        entry = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_through": "", "crashes": 0, "cells": 0}
    entry["status"] = "accepted" if accepted else "rejected"
    if fails:
        entry["reasons"] = fails
    if warns:
        entry["warnings"] = warns
    changed = []
    if accepted and "backtest_detail" in entry:  # a full run (not a download/rebuild failure)
        changed = artifacts_changed(BACKUP, HERE)
        entry["changed"] = changed
    text = render_report(entry, fails, warns)
    if not accepted:
        restore()
    print("\n" + text)
    if accepted and "backtest_detail" in entry and not changed and not args.force:
        restore()  # undo cosmetic noise (polygon digits, file order, re-run evaluation files)
        print("no material change: nothing new in the data, so all files were restored and nothing was written")
        if args.ci and os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("status=accepted\nchanged=false\n")
        return 0
    if args.dry_run:
        restore()
        print("dry run: all files restored, nothing written")
        return 0 if accepted else 1
    if accepted:  # only an accepted run advances the "previous crash list" used to find new crashes
        import build_risk as b
        if b.CSV_PATH.exists():
            shutil.copy2(b.CSV_PATH, b.CSV_PATH.with_name("crashes.prev.csv"))
    HISTORY.write_text(json.dumps(append_history(history, entry), indent=1))
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(text)
    if args.ci:
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as f:
                f.write(f"status={entry['status']}\nchanged={'true' if accepted and bool(changed) else 'false'}\n")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
