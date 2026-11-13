"""Fetch weather for all points (past 31 days + 8 forecast days) and the
soil-moisture climatology. Raw replies are cached; re-running is free.

Run:  uv run python -m shroomy.weather.fetch            # today's weather
      uv run python -m shroomy.weather.fetch --clim     # soil climatology (one-off)
"""
import json
import math
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np

from .. import config
from . import openmeteo
from .points import main_points, soil_points

OUT = config.PROCESSED / "weather"


def _daily_mean_from_hourly(times, values):
    """Hourly list -> {date: mean} (local days, as Open-Meteo returns them)."""
    out = {}
    for t, v in zip(times, values):
        if v is None:
            continue
        out.setdefault(t[:10], []).append(v)
    return {d: float(np.mean(v)) for d, v in out.items()}


def fetch_main(run_day: date | None = None, past_days: int | None = None, out_name: str = "run"):
    cfg = config.load("weather")["open_meteo"]
    caps = config.load("weather")["budget"]
    tz = ZoneInfo(cfg["timezone"])
    run_day = run_day or datetime.now(tz).date()
    pts = main_points()
    n = len(pts["lat"])
    past = cfg["past_days"] if past_days is None else past_days
    n_days = past + cfg["forecast_days"]
    n_vars = len(cfg["daily"]) + len(cfg["hourly"])
    per = cfg["locations_per_request"]
    est = openmeteo.call_cost(n, n_vars, n_days)
    print(f"{n} weather points · {n_days} days · ~{est:,.0f} calls")

    budget = openmeteo.Budget(caps)
    params = {"daily": ",".join(cfg["daily"]), "hourly": ",".join(cfg["hourly"]),
              "past_days": past, "forecast_days": cfg["forecast_days"],
              "models": cfg["model"], "timezone": cfg["timezone"]}
    raw_dir = config.RAW / "weather" / run_day.isoformat()
    results = []
    for b in range(math.ceil(n / per)):
        s = slice(b * per, (b + 1) * per)
        print(f" - batch {b + 1}/{math.ceil(n / per)}")
        results += openmeteo.fetch(cfg["forecast_url"], pts["lat"][s], pts["lon"][s], params,
                                   n_vars, n_days, budget, raw_dir / f"main_p{past}_v{n_vars}_b{b:03d}.json")

    dates = results[0]["daily"]["time"]
    arr = {v: np.full((n, len(dates)), np.nan, "float32") for v in cfg["daily"]}
    sm = np.full((n, len(dates)), np.nan, "float32")
    ts = np.full((n, len(dates)), np.nan, "float32")          # soil temperature 0-7 cm, model height
    elev = np.zeros(n, "float32")
    for i, r in enumerate(results):
        assert r["daily"]["time"] == dates
        for v in cfg["daily"]:
            arr[v][i] = [np.nan if x is None else x for x in r["daily"][v]]
        dm = _daily_mean_from_hourly(r["hourly"]["time"], r["hourly"][cfg["hourly"][0]])
        sm[i] = [dm.get(d, np.nan) for d in dates]
        if "soil_temperature_0_to_7cm" in r["hourly"]:
            dm = _daily_mean_from_hourly(r["hourly"]["time"], r["hourly"]["soil_temperature_0_to_7cm"])
            ts[i] = [dm.get(d, np.nan) for d in dates]
        elev[i] = r.get("elevation", np.nan)

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{out_name}_{run_day.isoformat()}.npz"
    np.savez_compressed(out, dates=np.array(dates), today=run_day.isoformat(),
                        lon=pts["lon"], lat=pts["lat"], x=pts["x"], y=pts["y"],
                        elev_om=elev, precip=arr["precipitation_sum"],
                        tmean=arr["temperature_2m_mean"], tmin=arr["temperature_2m_min"],
                        tmax=arr["temperature_2m_max"], rh=arr["relative_humidity_2m_mean"],
                        soil=sm, tsoil_om=ts, model=cfg["model"])
    print(f"Saved {out.name} · calls used in last 24 h: {budget.today():,.0f}")
    return out


def fetch_climatology():
    wcfg = config.load("weather")
    cfg, caps, clim = wcfg["open_meteo"], wcfg["budget"], wcfg["soil_climatology"]
    pts = soil_points()
    n = len(pts["lat"])
    budget = openmeteo.Budget(caps)
    values = [[] for _ in range(n)]
    total = 0.0
    for si, (start, end) in enumerate(clim["seasons"]):
        start, end = str(start), str(end)
        n_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        per_loc = openmeteo.call_cost(1, 1, n_days)
        per = max(1, int(caps["per_minute"] * 0.8 // per_loc))
        total += per_loc * n
        params = {"hourly": cfg["hourly"][0], "start_date": start, "end_date": end,
                  "models": cfg["model"], "timezone": cfg["timezone"]}
        for b in range(math.ceil(n / per)):
            s = slice(b * per, (b + 1) * per)
            print(f" - season {si + 1} batch {b + 1}/{math.ceil(n / per)}")
            res = openmeteo.fetch(cfg["history_url"], pts["lat"][s], pts["lon"][s], params,
                                  1, n_days, budget,
                                  config.RAW / "weather" / "clim" / f"s{si}_b{b:03d}.json")
            for j, r in enumerate(res):
                dm = _daily_mean_from_hourly(r["hourly"]["time"], r["hourly"][cfg["hourly"][0]])
                values[b * per + j] += list(dm.values())
    m = max(len(v) for v in values)
    mat = np.full((n, m), np.nan, "float32")
    for i, v in enumerate(values):
        mat[i, :len(v)] = np.sort(v)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / "soil_climatology.npz", lon=pts["lon"], lat=pts["lat"],
                        x=pts["x"], y=pts["y"], sorted_values=mat, seasons=json.dumps(clim["seasons"],
                        default=str), model=cfg["model"])
    print(f"{n} climatology points · ~{total:,.0f} calls · used in last 24 h: {budget.today():,.0f}")


if __name__ == "__main__":
    if "--clim" in sys.argv:
        fetch_climatology()
    else:
        fetch_main()
