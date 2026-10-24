"""Does the risk grid predict where FUTURE crashes happen?

    python backtest.py                    # train on <=2023, test on 2024+
    python backtest.py --train-until 2021

Builds the grid from crashes up to --train-until, then measures how the later crashes fall on it:
  - capture@N%: share of test crashes (and of test crash cost) landing in the top N% of train
    cells by risk. Higher is better; picking cells at random would capture ~N%.
  - spearman: rank correlation between train and test per-cell crash cost.
and compares weighting schemes, plus whether the left-turn layer predicts later left-turn crashes
better than the overall grid does.
"""
import argparse

import numpy as np
import pandas as pd

import build_risk as b


def _cells(gdf):
    return pd.Series(list(zip(np.floor(gdf.geometry.x / b.CELL_M).astype(int),
                              np.floor(gdf.geometry.y / b.CELL_M).astype(int))), index=gdf.index)


def _series(g, col):
    """Grid column as a Series indexed by (ix, iy) tuples."""
    return pd.Series(g[col].values, index=pd.Index(list(zip(g["ix"], g["iy"])), tupleize_cols=False))


def _capture(rank_score: pd.Series, test_cell_weight: pd.Series, pct: float) -> float:
    """Share of test weight in the top pct of cells by rank_score (cells indexed by (ix, iy))."""
    k = max(int(len(rank_score) * pct), 1)
    top = set(rank_score.sort_values(ascending=False).index[:k])
    total = test_cell_weight.sum()
    return float(test_cell_weight[test_cell_weight.index.isin(top)].sum() / total) if total else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-until", type=int, default=2023)
    args = ap.parse_args()
    if not b.CSV_PATH.exists():
        b.download(b.CSV_PATH)

    train = b.load_crashes(b.CSV_PATH, until=args.train_until)
    allc = b.load_crashes(b.CSV_PATH)
    test = allc[allc["date"].dt.year > args.train_until].copy()
    print(f"train: {len(train):,} crashes (<= {args.train_until}), test: {len(test):,} (later)\n")

    test["cell"] = _cells(test)
    test_cost = test.groupby("cell")["weight"].sum()
    test_n = test.groupby("cell").size()
    test_left_n = test[test["is_left"]].groupby("cell").size()

    schemes = {}
    for name, w in (("cost-weighted (default)", "cost"), ("severity-weighted", "severity")):
        g = b.build_grid(b.load_crashes(b.CSV_PATH, until=args.train_until, weights=w))
        schemes[name] = g
    counts = train.copy()
    counts["weight"] = 1.0
    schemes["crash count only"] = b.build_grid(counts)

    print(f"{'scheme':26s} {'cap@5% n':>9s} {'cap@10% n':>10s} {'cap@5% cost':>12s} {'cap@10% cost':>13s} {'spearman':>9s}")
    for name, g in schemes.items():
        s, train_w = _series(g, "risk"), _series(g, "weighted")
        both = pd.concat([train_w, test_cost], axis=1).fillna(0)
        rho = both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())
        print(f"{name:26s} {_capture(s, test_n, .05):9.1%} {_capture(s, test_n, .10):10.1%} "
              f"{_capture(s, test_cost, .05):12.1%} {_capture(s, test_cost, .10):13.1%} {rho:9.3f}")

    g = schemes["cost-weighted (default)"]
    overall, left = _series(g, "risk"), _series(g, "left_risk")
    print(f"\nleft-turn crashes in test: {int(test['is_left'].sum()):,}")
    print(f"{'ranking used':26s} {'cap@5% left':>12s} {'cap@10% left':>13s}")
    for name, s in (("overall risk", overall), ("left_risk layer", left)):
        print(f"{name:26s} {_capture(s, test_left_n, .05):12.1%} {_capture(s, test_left_n, .10):13.1%}")


if __name__ == "__main__":
    main()
