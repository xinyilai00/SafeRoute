import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import scoring  # noqa: E402
from app import app  # noqa: E402

# Straight line through downtown Austin and one through empty ranch land.
DOWNTOWN = [[-97.7431, 30.2672], [-97.7431, 30.2850]]
EMPTY = [[-98.05, 30.70], [-98.05, 30.72]]


def test_downtown_riskier_than_empty():
    assert scoring.score_route(DOWNTOWN, "car")[0] > scoring.score_route(EMPTY, "car")[0] == 0


def test_encoded_polyline_matches_coordinates():
    # classic Google doc example: (38.5,-120.2) (40.7,-120.95) (43.252,-126.453)
    assert scoring.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")[0] == (-120.2, 38.5)


def test_left_turn_penalised_more_on_bike_than_car():
    ins = [{"sign": 0, "interval": [0, 0], "distance": 500},
           {"sign": -2, "interval": [1, 1], "street_name": "Congress Ave", "distance": 100}]
    car, hz = scoring.score_route(DOWNTOWN, "car", ins)
    bike, _ = scoring.score_route(DOWNTOWN, "bike", ins)
    base_car, _ = scoring.score_route(DOWNTOWN, "car")
    assert car > base_car and bike > car
    assert any(h["type"] in ("left_turn", "left_turn_major") for h in hz)


def test_quick_turn_after_exit():
    near = [{"sign": 7, "interval": [0, 0], "text": "Take exit 235", "distance": 120},
            {"sign": 2, "interval": [1, 1], "distance": 100}]
    far = [{"sign": 7, "interval": [0, 0], "text": "Take exit 235", "distance": 2000},
           {"sign": 2, "interval": [1, 1], "distance": 100}]
    assert scoring.score_route(EMPTY, "car", near)[0] > scoring.score_route(EMPTY, "car", far)[0]


def test_risk_endpoint():
    c = TestClient(app)
    r = c.get("/risk")
    assert r.status_code == 200
    gj = r.json()
    assert gj["type"] == "FeatureCollection"
    assert all(0 <= f["properties"]["risk"] <= 1 for f in gj["features"])
