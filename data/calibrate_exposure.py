"""Pick EXPOSURE_POINTS_PER_RATE in scoring.py so the two crash models share one scale.

    python calibrate_exposure.py

On minor arterials and major collectors (TxDOT classes 4 and 5) the grid model and the exposure model should
give the same average points per mile; then the exposure model changes how roads COMPARE, not how big the scores
are. The constant is (average grid points per mile on those roads) / (average segment rate on those roads).
"""
import json

import numpy as np

import build_exposure as be
import scoring

REFERENCE_CLASSES = (4, 5)
STEP_M = 20.0


def main() -> None:
    attrs, lines = be.load_segments()
    rates = np.array(json.loads(be.RATES_PATH.read_text())["rate"])
    cells, cell_m, _ = scoring._grid()
    pts_per_mile, rate_per_mile, total_m = 0.0, 0.0, 0.0
    for a, line, rate in zip(attrs.itertuples(), lines, rates):
        if a.F not in REFERENCE_CLASSES:
            continue
        n = max(int(line.length // STEP_M), 1)
        for t in (np.arange(n) + 0.5) / n:
            p = line.interpolate(t, normalized=True)
            risk = scoring._lookup(cells, cell_m, p.x, p.y)[0]
            seg_m = line.length / n
            pts_per_mile += 10.0 * risk * seg_m / cell_m           # grid points for this stretch (crash weight 10)
            rate_per_mile += rate * seg_m / scoring.METERS_PER_MILE
            total_m += seg_m
    k = pts_per_mile / rate_per_mile
    print(f"{total_m / scoring.METERS_PER_MILE:,.0f} miles of classes {REFERENCE_CLASSES}: grid {pts_per_mile / (total_m / scoring.METERS_PER_MILE):.1f} points/mile, "
          f"mean rate {rate_per_mile / (total_m / scoring.METERS_PER_MILE):.1f} per 100M vehicle-miles")
    print(f"EXPOSURE_POINTS_PER_RATE = {k:.4f}")


if __name__ == "__main__":
    main()
