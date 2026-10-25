"""Measure how rain, low visibility and freezing temperatures change crash counts (Austin, 2014-2025).

    python analyze_weather.py            # downloads NOAA hourly files if missing, writes weather_effect.json

Method: every hour from 2014 to 2025 is labelled (rain / low visibility / freezing / dry) from the
Austin-Bergstrom ASOS station (NOAA GHCNh, USW00013904). Crashes are counted per hour. To compare fairly
we stratify by local hour-of-day x weekday/weekend: for each condition,
    expected = sum over that condition's hours of (crashes per hour in DRY hours of the same stratum)
    ratio    = observed / expected
so a ratio of 1.3 means 30% more crashes per hour than a dry hour at the same time of day.

Caveats: this is crashes per HOUR, not per vehicle-mile. Rain also reduces traffic, so the per-vehicle
effect is likely larger than the ratio shown. One airport station stands in for all of Austin.
"""
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

import build_risk as b

HERE = Path(__file__).parent
WEATHER_DIR = HERE / "raw" / "weather"
OUT_PATH = HERE / "weather_effect.json"
BASE = "https://noaa-ghcnh-pds.s3.us-east-1.amazonaws.com/hourly/access/by-year/{y}/psv/GHCNh_USW00013904_{y}.psv"
YEARS = range(2014, 2026)  # complete years only
WET_CODES = ("RA", "DZ", "TS", "SN", "SH", "GR", "PL", "FZ", "-RA", "-DZ", "+RA")
LOW_VIS_MILES = 3.0
FREEZING_C = 0.0
SHRINK_K = 20.0


def fetch(year: int) -> Path:
    WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    path = WEATHER_DIR / f"ghcnh_{year}.psv"
    if not path.exists():
        urllib.request.urlretrieve(BASE.format(y=year), path)
    return path


def hourly_conditions() -> pd.DataFrame:
    cols = ["DATE", "temperature", "precipitation", "visibility", "pres_wx_AW1", "pres_wx_MW1"]
    frames = [pd.read_csv(fetch(y), sep="|", usecols=cols, low_memory=False) for y in YEARS]
    df = pd.concat(frames)
    df["hour"] = pd.to_datetime(df["DATE"], utc=True, errors="coerce").dt.floor("h")
    df = df.dropna(subset=["hour"])

    def has_wet_code(s):
        return s.astype(str).str.upper().str.extract(r"^([+-]?[A-Z]{2})")[0].isin(WET_CODES)

    df["wet"] = (df["precipitation"] > 0) | has_wet_code(df["pres_wx_AW1"]) | has_wet_code(df["pres_wx_MW1"])
    df["lowvis"] = df["visibility"] < LOW_VIS_MILES
    df["freezing"] = df["temperature"] <= FREEZING_C
    g = df.groupby("hour").agg(wet=("wet", "max"), lowvis=("lowvis", "max"), freezing=("freezing", "max"))
    full = pd.date_range("2014-01-01", "2025-12-31 23:00", freq="h", tz="UTC")
    g = g.reindex(full)
    g[["wet", "lowvis", "freezing"]] = g[["wet", "lowvis", "freezing"]].fillna(False).astype(bool)
    return g


def crash_hours() -> pd.DataFrame:
    df = pd.read_csv(b.CSV_PATH, usecols=["id", "crash_timestamp_ct", "crash_sev_id", "collsn_desc", "is_deleted"])
    df = df[df["is_deleted"].astype(str).str.lower() != "true"]
    local = pd.to_datetime(df["crash_timestamp_ct"], errors="coerce")
    ts = local.dt.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT")
    df["hour"] = ts.dt.tz_convert("UTC").dt.floor("h")
    df = df.dropna(subset=["hour"])
    df = df[(df["hour"] >= "2014-01-01") & (df["hour"] < "2026-01-01")]
    df["ctype"] = df["collsn_desc"].map(b.crash_type)
    df["ksi"] = df["crash_sev_id"].isin([1, 4])
    return df


def ratio(hours: pd.DataFrame, per_hour: pd.Series, flag: str) -> dict:
    """observed/expected for hours where `flag` is true, vs dry hours of the same stratum."""
    local = hours.index.tz_convert("America/Chicago")
    stratum = pd.Series(np.asarray(local.hour) + 24 * np.asarray(local.dayofweek >= 5), index=hours.index)
    dry = ~(hours["wet"] | hours["lowvis"] | hours["freezing"])
    dry_rate = per_hour[dry].groupby(stratum[dry]).mean()
    sel = hours[flag]
    expected = float(stratum[sel].map(dry_rate).sum())
    observed = float(per_hour[sel].sum())
    r = observed / expected if expected else float("nan")
    se = 1 / math.sqrt(observed) if observed else float("nan")
    return {"hours": int(sel.sum()), "observed": int(observed), "expected": round(expected, 1),
            "ratio": round(r, 3), "ci95": [round(r * math.exp(-1.96 * se), 3), round(r * math.exp(1.96 * se), 3)],
            "shrunk": round((observed + SHRINK_K) / (expected + SHRINK_K), 3)}


def main() -> None:
    hours = hourly_conditions()
    crashes = crash_hours()
    print(f"{len(crashes):,} crashes, {len(hours):,} hours; wet {hours['wet'].mean():.1%}, "
          f"low-vis {hours['lowvis'].mean():.1%}, freezing {hours['freezing'].mean():.1%}")
    out = {"station": "USW00013904 (Austin-Bergstrom)", "years": [2014, 2025], "shrink_k": SHRINK_K,
           "note": "crashes per hour vs dry hours at the same local hour-of-day and weekday/weekend; not per vehicle-mile",
           "shares_of_hours": {k: round(float(hours[k].mean()), 4) for k in ("wet", "lowvis", "freezing")}}
    series = {"all": crashes.groupby("hour").size(), "ksi": crashes[crashes["ksi"]].groupby("hour").size()}
    for t in b.TYPES:
        series[t] = crashes[crashes["ctype"] == t].groupby("hour").size()
    for name, s in series.items():
        per_hour = s.reindex(hours.index, fill_value=0).astype(float)
        out[name] = {flag: ratio(hours, per_hour, flag) for flag in ("wet", "lowvis", "freezing")}
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"{'crashes':20s} {'rain ratio (95% CI)':>26s} {'low-vis':>22s} {'freezing':>22s}")
    for name in series:
        row = out[name]
        f = lambda k: f"{row[k]['ratio']:4.2f} ({row[k]['ci95'][0]:.2f}-{row[k]['ci95'][1]:.2f}) n={row[k]['observed']}"
        print(f"{name:20s} {f('wet'):>26s} {f('lowvis'):>22s} {f('freezing'):>22s}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
