import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import refresh as R  # noqa: E402


def grid(n=400, scale=1.0, drop=None):
    """A tiny synthetic grid: squares in a line with rising risk, top square exactly 1.0."""
    feats = []
    for i in range(n):
        risk = min(1.0, (i + 1) / n * scale)
        p = {"ix": i, "iy": 0, "risk": round(risk, 4), "left_risk": 0.1, "risk_teen": risk, "risk_elderly": risk}
        feats.append({"type": "Feature", "properties": p, "geometry": None})
    if drop:
        feats = feats[:-drop]
        feats[-1]["properties"]["risk"] = 1.0
    return {"type": "FeatureCollection", "features": feats}


def good_checks(**over):
    c = {"structure": [], "similarity": 0.999, "backtest": 0.58, "tests_ok": True,
         "route": {"pair_concordance": 0.63, "profiles": {"teen": {"held_change_pct": -4.1}, "elderly": {"held_change_pct": -4.8}}},
         "forward": {"n": 100, "hits": 55, "capture": 0.55, "ci": [0.45, 0.65]}}
    c.update(over)
    return c


# ---- wilson interval ----

def test_wilson_basic_properties():
    lo, hi = R.wilson(50, 100)
    assert lo < 0.5 < hi and 0.40 < lo and hi < 0.60
    assert R.wilson(0, 0) == (0.0, 1.0)
    assert R.wilson(100, 100)[1] == pytest.approx(1.0) and R.wilson(100, 100)[0] > 0.95
    assert R.wilson(10, 1000)[1] - R.wilson(10, 1000)[0] < R.wilson(1, 100)[1] - R.wilson(1, 100)[0]  # more data, tighter


# ---- structure and similarity ----

def test_structure_accepts_a_good_grid_and_flags_bad_ones():
    prev = grid(400)
    assert R.check_structure(grid(410), prev) == []
    assert any("no squares" in p for p in R.check_structure({"features": []}, prev))
    g = grid(400)
    g["features"][5]["properties"]["risk"] = 1.5
    assert any("outside 0..1" in p for p in R.check_structure(g, prev))
    g = grid(400)
    del g["features"][3]["properties"]["risk_teen"]
    assert any("risk_teen" in p for p in R.check_structure(g, prev))
    g = grid(400)
    g["features"][1]["properties"]["ix"] = 0                      # duplicate square
    assert any("duplicate" in p for p in R.check_structure(g, prev))
    assert any("square count" in p for p in R.check_structure(grid(200), prev))         # half as many squares
    assert any("normalised" in p for p in R.check_structure(grid(400, scale=0.5), prev))


def test_similarity():
    a = grid(400)
    assert R.similarity(a, a) == pytest.approx(1.0)
    b = grid(400)
    for i, f in enumerate(b["features"]):                          # reversed ranking: totally different
        f["properties"]["risk"] = a["features"][-1 - i]["properties"]["risk"]
    assert R.similarity(b, a) < 0
    assert R.similarity(grid(50), grid(50)) is None                # too few common squares to judge


# ---- forward check ----

def test_forward_capture_ranks_new_crashes_against_the_old_grid():
    prev = grid(400)                                               # top 10% = squares 360..399
    top = [(i, 0) for i in range(360, 400)]
    out = R.forward_capture(prev, top)
    assert out["n"] == 40 and out["hits"] == 40 and out["capture"] == 1.0
    bottom = [(i, 0) for i in range(0, 40)]
    assert R.forward_capture(prev, bottom)["capture"] == 0.0
    mixed = R.forward_capture(prev, top[:10] + bottom[:30])
    assert mixed["capture"] == pytest.approx(0.25) and mixed["ci"][0] < 0.25 < mixed["ci"][1]
    assert R.forward_capture(prev, [(9999, 9999)])["hits"] == 0     # unknown square counts as a miss
    assert R.forward_capture(prev, [])["capture"] is None


# ---- the gate ----

def test_gate_accepts_a_healthy_run():
    ok, fails, warns = R.decide(good_checks(), None)
    assert ok and fails == [] and warns == []


@pytest.mark.parametrize("override, expect", [
    ({"structure": ["grid has no squares"]}, "no squares"),
    ({"similarity": 0.80}, "differs too much"),
    ({"backtest": 0.45}, "below the floor"),
    ({"tests_ok": False}, "unit tests failed"),
    ({"route": {"pair_concordance": 0.50, "profiles": {"teen": {"held_change_pct": -4.0}}}}, "no longer predicts"),
    ({"route": {"pair_concordance": 0.63, "profiles": {"teen": {"held_change_pct": -0.5}}}}, "no longer meaningfully safer"),
])
def test_gate_rejects_each_kind_of_problem(override, expect):
    ok, fails, _ = R.decide(good_checks(**override), None)
    assert not ok and any(expect in f for f in fails)


def test_gate_compares_with_the_last_accepted_run():
    last = {"backtest": 0.58, "route": {"profiles": {"teen": {"held_change_pct": -4.1}, "elderly": {"held_change_pct": -4.8}}}}
    ok, fails, _ = R.decide(good_checks(backtest=0.57), last)           # small dip: fine
    assert ok
    ok, fails, _ = R.decide(good_checks(backtest=0.53), last)           # above the floor but dropped 5 points
    assert not ok and any("fell" in f for f in fails)
    worse = {"pair_concordance": 0.63, "profiles": {"teen": {"held_change_pct": -1.9}, "elderly": {"held_change_pct": -4.8}}}
    ok, fails, _ = R.decide(good_checks(route=worse), last)             # still safer, but regressed > 2 points
    assert not ok and any("regressed" in f for f in fails)


def test_drift_is_only_a_warning():
    drifting = {"n": 300, "hits": 40, "capture": 0.13, "ci": [0.10, 0.17]}
    ok, fails, warns = R.decide(good_checks(forward=drifting), None)
    assert ok and not fails and len(warns) == 1 and "drift" in warns[0]
    quiet = {"n": 5, "hits": 0, "capture": 0.0, "ci": [0.0, 0.43]}      # too few crashes to say anything
    assert R.decide(good_checks(forward=quiet), None)[2] == []


# ---- history ----

def test_history_helpers():
    h = []
    for i in range(5):
        h = R.append_history(h, {"i": i, "status": "accepted" if i % 2 == 0 else "rejected"}, keep=3)
    assert [e["i"] for e in h] == [2, 3, 4]
    assert R.last_accepted(h)["i"] == 4
    assert R.last_accepted([{"status": "rejected"}]) is None


# ---- backup / restore ----

def test_restore_undoes_a_bad_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "HERE", tmp_path)
    monkeypatch.setattr(R, "BACKUP", tmp_path / "raw" / "refresh_backup")
    monkeypatch.setattr(R, "ARTIFACTS", ["risk.geojson", "eval/metrics.json"])
    (tmp_path / "eval").mkdir()
    (tmp_path / "risk.geojson").write_text("OLD GRID")
    (tmp_path / "eval" / "metrics.json").write_text("OLD METRICS")
    R.backup()
    (tmp_path / "risk.geojson").write_text("BROKEN")
    (tmp_path / "eval" / "metrics.json").unlink()
    R.restore()
    assert (tmp_path / "risk.geojson").read_text() == "OLD GRID"
    assert (tmp_path / "eval" / "metrics.json").read_text() == "OLD METRICS"


def test_report_mentions_status_reasons_and_numbers():
    entry = {"date": "2026-11-01T09:00:00+00:00", "status": "rejected", "data_through": "2026-10-30T00:00:00", "crashes": 233000,
             "cells": 9650, "similarity": 0.97, "backtest": 0.58, "backtest_detail": {"train_until": 2024, "test_crashes": 20000},
             "forward": {"n": 100, "hits": 55, "capture": 0.55, "ci": [0.45, 0.65]}, "new_crashes_note": "ids not in the previous download",
             "route": {"trips": 200, "held_out_crashes": 32000, "pair_concordance": 0.63,
                       "profiles": {"teen": {"changed_share": 0.18, "minutes_added": 0.23, "held_change_pct": -4.1}}},
             "tests": "46 passed"}
    text = R.render_report(entry, ["backtest capture fell"], ["drift: example"])
    for needle in ("REJECTED", "backtest capture fell", "drift: example", "55%", "58.0%", "-4.1%", "46 passed", "233,000"):
        assert needle in text


def test_rolling_backtest_and_forward_check_run_on_real_data():
    """Smoke test on the actual files: the numbers should be in a sane range (skips if raw data absent)."""
    import build_risk as b
    if not b.CSV_PATH.exists():
        pytest.skip("raw crash CSV not downloaded")
    bt = R.rolling_backtest()
    assert 0.40 < bt["capture10"] < 0.80 and bt["test_crashes"] > 1000
    prev = json.loads(R.GRID.read_text())
    cells, _ = R.new_crash_cells(prev)
    assert isinstance(cells, list)


# ---------- "did anything real change?" (cosmetic differences must not trigger a pull request) ----------

def _write_artifacts(d, grid_coords=0.0, signals=None, pave=None, ratios=None, weather=None, risk=0.5, built="2026-10-25", seg_rate=100.0):
    d.mkdir(parents=True, exist_ok=True)
    feats = [{"type": "Feature", "properties": {"ix": i, "iy": 0, "risk": risk if i == 3 else 0.1, "left_risk": 0.0,
                                                "risk_teen": 0.1, "risk_elderly": 0.1},
              "geometry": {"type": "Polygon", "coordinates": [[[i + grid_coords, 0.0], [i + 1, 0.0], [i, 1.0]]]}} for i in range(10)]
    (d / "risk.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats, "meta": {"built_at": built}}))
    (d / "signals.json").write_text(json.dumps(signals or [[-97.7, 30.2], [-97.8, 30.3], [-97.6, 30.1]]))
    (d / "street_condition.json").write_text(json.dumps(pave or [["F", 500, [[-97.7, 30.2], [-97.71, 30.21]]], ["A", 90, [[-97.8, 30.3], [-97.81, 30.31]]]]))
    (d / "profile_ratios.json").write_text(json.dumps(ratios or {"teen": {"ratios": {"left-turn": 0.96}}}))
    (d / "weather_effect.json").write_text(json.dumps(weather or {"all": {"wet": {"ratio": 1.43}}}))
    (d / "segment_rates.json").write_text(json.dumps({"meta": {}, "rate": [seg_rate, 12.0, 20.0], "teen": [seg_rate, 12.0, 20.0],
                                                      "elderly": [seg_rate, 12.0, 20.0]}))


def test_cosmetic_differences_are_not_a_change(tmp_path):
    prev, cur = tmp_path / "prev", tmp_path / "cur"
    _write_artifacts(prev)
    # different polygon digits (macOS vs Linux projections), different build time, signals and pavement reordered
    _write_artifacts(cur, grid_coords=1e-9, built="2026-11-01",
                     signals=[[-97.6, 30.1], [-97.7, 30.2], [-97.8, 30.3]],
                     pave=[["A", 90, [[-97.8, 30.3], [-97.81, 30.31]]], ["F", 500, [[-97.7, 30.2], [-97.71, 30.21]]]])
    assert R.artifacts_changed(prev, cur) == []


@pytest.mark.parametrize("override, expect", [
    ({"risk": 0.6}, "risk grid"),
    ({"signals": [[-97.7, 30.2], [-97.8, 30.3]]}, "signals"),
    ({"pave": [["F", 500, [[-97.7, 30.2], [-97.71, 30.21]]], ["D", 90, [[-97.8, 30.3], [-97.81, 30.31]]]]}, "street condition"),
    ({"ratios": {"teen": {"ratios": {"left-turn": 1.05}}}}, "profile ratios"),
    ({"weather": {"all": {"wet": {"ratio": 1.5}}}}, "weather effect"),
    ({"seg_rate": 120.0}, "segment rates"),
])
def test_real_differences_are_detected(tmp_path, override, expect):
    prev, cur = tmp_path / "prev", tmp_path / "cur"
    _write_artifacts(prev)
    _write_artifacts(cur, **override)
    assert R.artifacts_changed(prev, cur) == [expect]


def test_tiny_rate_drift_is_noise_but_a_real_move_is_not(tmp_path):
    prev, cur = tmp_path / "prev", tmp_path / "cur"
    _write_artifacts(prev, seg_rate=100.0)
    _write_artifacts(cur, seg_rate=100.4)                          # 0.4%: platform noise
    assert R.artifacts_changed(prev, cur) == []
    _write_artifacts(cur, seg_rate=103.0)                          # 3%: a real change
    assert R.artifacts_changed(prev, cur) == ["segment rates"]


def test_grid_cell_added_or_missing_file_counts_as_change(tmp_path):
    prev, cur = tmp_path / "prev", tmp_path / "cur"
    _write_artifacts(prev)
    _write_artifacts(cur)
    g = json.loads((cur / "risk.geojson").read_text())
    g["features"].pop()                                           # a square disappears
    (cur / "risk.geojson").write_text(json.dumps(g))
    assert "risk grid" in R.artifacts_changed(prev, cur)
    (cur / "signals.json").unlink()                               # a missing file is a change, not a crash
    assert "signals" in R.artifacts_changed(prev, cur)


def test_signals_builder_output_is_sorted():
    src = (Path(__file__).parent.parent / "build_signals.py").read_text()
    assert "pts.sort()" in src


# ---------- the gate judges "safer" by the metric that matches the crash model ----------

def pv_route(change=-20.0, conc=0.65, model="exposure"):
    return {"model": model, "primary_metric": "pv", "pair_concordance": conc,
            "profiles": {"teen": {"primary_change_pct": change, "pv_change_pct": change, "held_change_pct": -0.5},
                         "elderly": {"primary_change_pct": change, "pv_change_pct": change, "held_change_pct": -0.5}}}


def test_per_vehicle_metric_is_used_for_the_exposure_model():
    # crashes counted along the route barely moved (-0.5%), which would fail the old rule; per-vehicle risk fell 20%
    ok, fails, _ = R.decide(good_checks(route=pv_route(-20.0)), None)
    assert ok and fails == []
    ok, fails, _ = R.decide(good_checks(route=pv_route(-5.0)), None)       # only 5% safer per vehicle: below the -8% bar
    assert not ok and any("per-vehicle crash risk" in f and "no longer meaningfully safer" in f for f in fails)


def test_per_vehicle_regression_is_compared_only_on_the_same_basis():
    last = {"route": pv_route(-22.0)}
    ok, fails, _ = R.decide(good_checks(route=pv_route(-17.0)), last)      # fell 5 points: more than the 4-point tolerance
    assert not ok and any("regressed" in f for f in fails)
    ok, _, _ = R.decide(good_checks(route=pv_route(-19.0)), last)          # fell 3 points: within tolerance
    assert ok
    old_grid_entry = {"route": {"model": "grid", "primary_metric": "held", "profiles": {"teen": {"primary_change_pct": -4.1}}}}
    ok, _, _ = R.decide(good_checks(route=pv_route(-10.0)), old_grid_entry)  # different basis: no regression comparison
    assert ok


def test_old_style_metrics_without_primary_fields_still_work():
    ok, fails, _ = R.decide(good_checks(), None)                           # good_checks has only held_change_pct
    assert ok and not fails
