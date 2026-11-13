"""Fill the weather history back to 1 September, once (audit step 4: season memory).

The daily run only ever adds a few days, so a new history starts with 31 past days.
This fetches the missing days from 1 September of the season up to the oldest day
already in the store, from the Open-Meteo historical-forecast API (same model, same points),
and merges them in as observed days.

Cost: about (points) x (days / 14) calls; 1,159 points x 41 days = about 3,400.
It refuses to start if that would go over the daily budget.

Run:  uv run python -m shroomy.weather.backfill [--cost]
"""
import math
import sys
from datetime import date, timedelta

import numpy as np

from .. import config
from . import history, openmeteo
from .fetch import _daily_mean_from_hourly

DAILY = ["precipitation_sum", "temperature_2m_mean", "temperature_2m_min", "temperature_2m_max",
         "relative_humidity_2m_mean"]
KEYS = {"precipitation_sum": "precip", "temperature_2m_mean": "tmean", "temperature_2m_min": "tmin",
        "temperature_2m_max": "tmax", "relative_humidity_2m_mean": "rh"}


def plan(today=None, store=history.STORE):
    """(start, end, points, cost) of the missing stretch, or None if nothing is missing."""
    h = np.load(store)
    dates = sorted(str(d) for d in h["dates"])
    today = today or date.fromisoformat(str(h["last_run"]))
    start = history.season_start(today)
    end = date.fromisoformat(dates[0]) - timedelta(days=1)
    if end < start:
        return None
    n_days = (end - start).days + 1
    cost = openmeteo.call_cost(len(h["lon"]), len(DAILY) + 2, n_days)
    return start, end, h, cost


def backfill(store=history.STORE):
    p = plan(store=store)
    if p is None:
        print("History already reaches 1 September.")
        return None
    start, end, h, cost = p
    wcfg = config.load("weather")
    cfg, caps = wcfg["open_meteo"], wcfg["budget"]
    budget = openmeteo.Budget(caps)
    if budget.today() + cost > caps["per_day"]:
        raise RuntimeError(f"needs ~{cost:,.0f} calls; {budget.today():,.0f} of {caps['per_day']:,} used in the "
                           "last 24 h. Try later.")
    n = len(h["lon"])
    n_days = (end - start).days + 1
    per_loc = cost / n
    per = max(1, int(caps["per_minute"] * 0.8 // per_loc))
    params = {"daily": ",".join(DAILY), "hourly": "soil_moisture_0_to_7cm,soil_temperature_0_to_7cm",
              "start_date": start.isoformat(),
              "end_date": end.isoformat(), "models": cfg["model"], "timezone": cfg["timezone"]}
    print(f"Backfill {start} to {end}: {n} points, ~{cost:,.0f} calls")
    res = []
    for b in range(math.ceil(n / per)):
        s = slice(b * per, (b + 1) * per)
        print(f" - batch {b + 1}/{math.ceil(n / per)}")
        res += openmeteo.fetch(cfg["history_url"], h["lat"][s], h["lon"][s], params, len(DAILY) + 2, n_days,
                               budget, config.RAW / "weather" / "backfill" / f"{start}_{end}_b{b:03d}.json")
    dates = res[0]["daily"]["time"]
    out = {k: h[k] for k in history.POINT_KEYS}
    for v in DAILY:
        out[KEYS[v]] = np.array([[np.nan if x is None else x for x in r["daily"][v]] for r in res], "float32")
    out["soil"] = np.array([[_daily_mean_from_hourly(r["hourly"]["time"], r["hourly"]["soil_moisture_0_to_7cm"])
                             .get(d, np.nan) for d in dates] for r in res], "float32")
    out["tsoil_om"] = np.array([[_daily_mean_from_hourly(r["hourly"]["time"], r["hourly"]["soil_temperature_0_to_7cm"])
                                 .get(d, np.nan) for d in dates] for r in res], "float32")
    run = config.PROCESSED / "weather" / f"backfill_{start}_{end}.npz"
    # today = the day after the stretch, so every day in it counts as observed.
    np.savez_compressed(run, dates=np.array(dates), today=(end + timedelta(days=1)).isoformat(),
                        model=h["model"], **out)
    keep_last = str(h["last_run"])
    merged = history.merge(run, store)
    if keep_last > str(merged["last_run"]):            # merge() stamps last_run from the run file
        z = dict(np.load(store))
        z["last_run"] = np.array(keep_last)
        np.savez_compressed(store, **z)
    print(f"History now {len(merged['dates'])} days, from {merged['dates'][0]}")
    return run


if __name__ == "__main__":
    if "--cost" in sys.argv:
        p = plan()
        print("nothing missing" if p is None else f"{p[0]} to {p[1]}: ~{p[3]:,.0f} calls")
    else:
        backfill()
