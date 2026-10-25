"""Current Austin weather for a heads-up (not used in route scoring).

`current()` returns {"raining": bool, "low_visibility": bool, "freezing": bool, "source": "open-meteo"}
or None when the weather can't be fetched. Cached for CACHE_S seconds; a failure is cached briefly so
a down API can't slow every /route. Disable with WEATHER_DISABLED=1 (tests do).

Source: Open-Meteo (free, no key for non-commercial use), https://open-meteo.com/en/docs. The measured
effect of rain on Austin crash counts lives in weather_effect.json (analyze_weather.py): about 43% more
crashes per hour than a dry hour at the same time of day. It is NOT folded into the risk grid: rain
barely changes which squares are riskiest relative to each other (the rain-weighted grid correlates
0.995 with the normal one), so it would not change which route wins.
"""
import json
import os
import threading
import time
from pathlib import Path

import httpx

URL = "https://api.open-meteo.com/v1/forecast"
LAT, LNG = 30.2672, -97.7431     # downtown Austin; one point stands in for the pilot area
CACHE_S, FAIL_CACHE_S, TIMEOUT_S = 600, 60, 4.0
LOW_VISIBILITY_M = 4828.0        # 3 miles, same threshold as analyze_weather.py
EFFECT_PATH = Path(__file__).parent / "weather_effect.json"
# WMO weather codes: drizzle 51-57, rain 61-67, rain showers 80-82, thunderstorm 95-99, freezing precipitation 56/57/66/67
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}

_lock = threading.Lock()
_cache = {"expires": 0.0, "value": None}


def _classify(cur: dict) -> dict:
    code = cur.get("weather_code")
    vis = cur.get("visibility")
    temp = cur.get("temperature_2m")
    return {
        "raining": bool((cur.get("precipitation") or 0) > 0 or (cur.get("rain") or 0) > 0 or code in RAIN_CODES),
        "low_visibility": vis is not None and vis < LOW_VISIBILITY_M,
        "freezing": temp is not None and temp <= 0.0,
        "source": "open-meteo",
    }


def current():
    if os.environ.get("WEATHER_DISABLED"):
        return None
    now = time.time()
    with _lock:
        if _cache["expires"] > now:
            return _cache["value"]
    value, ttl = None, FAIL_CACHE_S
    try:
        r = httpx.get(URL, timeout=TIMEOUT_S, params={
            "latitude": LAT, "longitude": LNG, "timezone": "America/Chicago",
            "current": "temperature_2m,precipitation,rain,weather_code,visibility"})
        r.raise_for_status()
        value, ttl = _classify(r.json()["current"]), CACHE_S
    except Exception as e:  # network, rate limit, bad payload: just no heads-up
        print(f"weather: Open-Meteo failed ({type(e).__name__})")
    with _lock:
        _cache.update(expires=now + ttl, value=value)
    return value


def rain_crash_ratio():
    """Measured crashes-per-hour ratio for rain vs a dry hour at the same time of day, or None."""
    try:
        return json.loads(EFFECT_PATH.read_text())["all"]["wet"]["ratio"]
    except Exception:
        return None
