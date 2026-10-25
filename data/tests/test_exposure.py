import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).parent.parent))

import build_exposure as be  # noqa: E402
import scoring  # noqa: E402


# ---------------------------------------------------------------- build_exposure maths

def test_decay_weights_and_exposure_units():
    w = be.decay_weights(2020, 2025, halflife=5.0)
    assert w[-1] == pytest.approx(1.0) and w[0] == pytest.approx(0.5)            # 5 years back counts half
    import pandas as pd
    attrs = pd.DataFrame({"adt": [10000.0], "miles": [0.5]})
    per_year = 10000 * 0.5 * 365 / 1e8                                          # 100M vehicle-miles per year
    assert be.exposure(attrs, 2020, 2020)[0] == pytest.approx(per_year)
    assert be.exposure(attrs, 2020, 2025)[0] == pytest.approx(per_year * w.sum())


def test_empirical_bayes_interpolates_between_raw_and_class_rate():
    klass = np.array([4, 4, 4, 1])
    expo = np.array([1.0, 1.0, 1.0, 1.0])
    obs = np.array([300.0, 100.0, 0.0, 10.0])                                   # class 4 pooled rate = 400 / 3
    raw, prior = be.eb_rates(obs, expo, klass, 0.0)
    assert raw.tolist() == [300.0, 100.0, 0.0, 10.0]
    assert prior[4] == pytest.approx(400 / 3) and prior[1] == pytest.approx(10.0)
    class_only, _ = be.eb_rates(obs, expo, klass, 1e9)
    assert class_only[:3] == pytest.approx([400 / 3] * 3)
    mid, _ = be.eb_rates(obs, expo, klass, 1.0)
    assert mid[0] == pytest.approx((300 + 400 / 3) / 2)                         # half way between raw and class
    assert raw[0] > mid[0] > class_only[0] and raw[2] < mid[2] < class_only[2]  # extremes pulled toward the class rate


def test_crashes_match_the_nearest_segment_within_tolerance():
    from pyproj import Transformer
    to = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
    x0, y0 = to.transform(-97.70, 30.30)
    from shapely.geometry import LineString
    lines = [LineString([(x0, y0), (x0, y0 + 500)]), LineString([(x0 + 200, y0), (x0 + 200, y0 + 500)])]
    pts = [Point(x0 + 5, y0 + 100), Point(x0 + 190, y0 + 300), Point(x0 + 100, y0 + 100), Point(x0 + 600, y0)]
    crashes = types.SimpleNamespace(geometry=types.SimpleNamespace(values=np.array(pts, dtype=object)))
    assert be.match_crashes(lines, crashes).tolist() == [0, 1, -1, -1]          # 100 m from both and 400 m away: unmatched


def test_real_rates_file_is_consistent_with_the_segment_file():
    segs = json.loads(be.SEGMENTS_PATH.read_text())["segments"]
    rates = json.loads(be.RATES_PATH.read_text())
    n = len(segs)
    assert n > 10000 and all(len(rates[k]) == n for k in ("rate", "teen", "elderly"))
    by_class = {}
    for seg, r in zip(segs, rates["rate"]):
        by_class.setdefault(seg[0], []).append(r)
    mean = {k: float(np.mean(v)) for k, v in by_class.items()}
    assert mean[1] < mean[4] and mean[2] < mean[4] and mean[2] < mean[5]         # freeways: far lower per-vehicle rate than arterials


# ---------------------------------------------------------------- scoring with the exposure model

FREEWAY = [[-98.0500, 30.7000], [-98.0500, 30.7100]]      # about 1.1 km, north-south, in empty land (no grid risk)
ARTERIAL = [[-98.0450, 30.7000], [-98.0450, 30.7100]]     # 500 m east of it


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    """Two TxDOT-style segments in empty land: a freeway (low rate) and an arterial (high rate)."""
    segs = [[1, 100000, 70, 3, 0, 0, 0.69, FREEWAY], [4, 20000, 45, 2, 0, 0, 0.69, ARTERIAL]]
    rates = {"meta": {"class_rate_per_100M_vmt": {"1": 15.0, "4": 100.0}},
             "rate": [15.0, 300.0], "teen": [15.0, 300.0], "elderly": [15.0, 300.0]}
    (tmp_path / "segs.json").write_text(json.dumps({"segments": segs}))
    (tmp_path / "rates.json").write_text(json.dumps(rates))
    monkeypatch.setattr(scoring, "SEGMENTS_PATH", tmp_path / "segs.json")
    monkeypatch.setattr(scoring, "RATES_PATH", tmp_path / "rates.json")
    monkeypatch.setenv("RISK_MODEL", "exposure")
    scoring._segments.cache_clear()
    yield
    scoring._segments.cache_clear()


def test_exposure_points_are_rate_times_distance(synthetic):
    pts, _ = scoring.crash_risk(FREEWAY, "teen", road_classes=[[0, 1, "motorway"]])
    miles = 0.69
    assert pts == pytest.approx(scoring.EXPOSURE_POINTS_PER_RATE * 15.0 * miles, rel=0.08)
    arterial, hz = scoring.crash_risk(ARTERIAL, "teen", road_classes=[[0, 1, "secondary"]])
    assert arterial == pytest.approx(scoring.EXPOSURE_POINTS_PER_RATE * 300.0 * miles, rel=0.08)
    assert arterial > 15 * pts                                                   # the per-vehicle gap is carried through
    assert any(h["type"] == "high_crash_zone" and "3.0x" in h["description"] for h in hz)   # 300 vs class rate 100


def test_a_frontage_road_never_borrows_a_freeways_rate(synthetic):
    freeway_stretch, _ = scoring.crash_risk(FREEWAY, "car", road_classes=[[0, 1, "motorway"]])
    on_frontage, _ = scoring.crash_risk(FREEWAY, "car", road_classes=[[0, 1, "secondary"]])   # GraphHopper says: not a motorway
    assert freeway_stretch > 0 and on_frontage == 0.0                            # falls back to the (empty) grid


def test_samples_off_any_segment_fall_back_to_the_grid(synthetic):
    off = [[-98.0350, 30.7000], [-98.0350, 30.7100]]                             # 1.5 km from both segments, empty land
    assert scoring.crash_risk(off, "car")[0] == 0.0
    downtown = [[-97.7431, 30.2672], [-97.7431, 30.2850]]                        # real grid cells, no synthetic segment nearby
    assert scoring.crash_risk(downtown, "car")[0] > 0


def test_mismatched_rate_file_falls_back_to_the_grid(tmp_path, monkeypatch):
    (tmp_path / "segs.json").write_text(json.dumps({"segments": [[1, 100000, 70, 3, 0, 0, 0.69, FREEWAY]]}))
    (tmp_path / "rates.json").write_text(json.dumps({"meta": {"class_rate_per_100M_vmt": {"1": 15.0}}, "rate": [1.0, 2.0],
                                                     "teen": [1.0, 2.0], "elderly": [1.0, 2.0]}))   # two rates for one segment
    monkeypatch.setattr(scoring, "SEGMENTS_PATH", tmp_path / "segs.json")
    monkeypatch.setattr(scoring, "RATES_PATH", tmp_path / "rates.json")
    monkeypatch.setenv("RISK_MODEL", "exposure")
    scoring._segments.cache_clear()
    assert scoring._segments() is None and scoring._exposure_model("car") is None
    assert scoring.crash_risk(FREEWAY, "car")[0] == 0.0                          # no crash: just the grid result
    scoring._segments.cache_clear()


def test_exposure_is_the_default_and_the_grid_model_still_works(monkeypatch):
    monkeypatch.delenv("RISK_MODEL", raising=False)
    assert scoring.DEFAULT_RISK_MODEL == "exposure" and scoring._use_exposure()
    monkeypatch.setenv("RISK_MODEL", "grid")
    assert not scoring._use_exposure()
    line = [[-97.7431, 30.2672], [-97.7431, 30.2850]]
    grid_pts, _ = scoring.crash_risk(line, "car")
    monkeypatch.setenv("RISK_MODEL", "exposure")
    scoring._segments.cache_clear()
    assert scoring.crash_risk(line, "car")[0] != grid_pts                       # the two models genuinely differ downtown


def test_route_endpoint_works_under_the_exposure_model(monkeypatch):
    from fastapi.testclient import TestClient
    from app import app
    monkeypatch.setenv("RISK_MODEL", "exposure")
    scoring._segments.cache_clear()
    body = {"origin": {"lat": 30.2849, "lng": -97.7341}, "destination": {"lat": 30.2672, "lng": -97.7431}, "profile": "elderly"}
    r = TestClient(app).post("/route", json=body)
    assert r.status_code == 200
    out = r.json()
    assert set(out) == {"fastest", "safest", "comparison"} and out["fastest"]["risk_score"] >= 0
