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
