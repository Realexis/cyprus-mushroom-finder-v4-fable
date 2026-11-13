"""Backtest the v0.3 species engine on the 2025-26 season (spec section 5).

1. Fetch daily rain + temperature for the season on the ~9 km weather grid (one point per
   9 km land block = the ECMWF model's own size). Cached in data/raw/weather/backtest/.
2. Run every species profile over the whole season on a sample of habitat squares.
3. Compare with dated public records in Cyprus (iNaturalist research grade + GBIF) and
   with what the press reported (a poor season: rain came late and cold).

Output: data/processed/backtest/backtest_2025-26.json (+ the report is written by hand
from it into docs/backtest-2025-26.md).

Run:  uv run python -m shroomy.backtest [--fetch-only]
"""
import json
import math
import sys
from datetime import date, timedelta

import numpy as np
import requests

from . import config
from .engine import inputs as I
from .engine import profile as P
from .engine.cycle import OPEN, STATE_NAMES
from .engine.daily import habitat_all
from .engine.runner import prepare_water, run_species
from .grid import habitat_grid
from .weather import openmeteo
from .weather.points import _habitat, _to_table, block_points

START, END = "2025-09-01", "2026-02-28"
CACHE = config.RAW / "weather" / "backtest"
OUT = config.PROCESSED / "backtest"
VARS = ["precipitation_sum", "temperature_2m_mean", "temperature_2m_min", "temperature_2m_max"]
SAMPLE_EVERY = 4                                  # every 4th habitat square (keeps memory small)
HEADERS = {"User-Agent": "cyprus-mushroom-finder/0.1 (non-commercial, static site)"}
INAT_CYPRUS = "10289,96773"


def season_points():
    g = habitat_grid()
    hab = _habitat()
    k = int(config.load("weather")["soil_climatology"]["block_km"] * 1000 / g.res)
    return _to_table(block_points(hab["land_fraction"] > 0.5, k), g)


def fetch_season():
    wcfg = config.load("weather")
    cfg, caps = wcfg["open_meteo"], wcfg["budget"]
    pts = season_points()
    n = len(pts["lat"])
    n_days = (date.fromisoformat(END) - date.fromisoformat(START)).days + 1
    per_loc = openmeteo.call_cost(1, len(VARS), n_days)
    print(f"{n} points x {n_days} days: ~{per_loc * n:,.0f} calls")
    budget = openmeteo.Budget(caps)
    per = max(1, int(caps["per_minute"] * 0.8 // per_loc))
    params = {"daily": ",".join(VARS), "start_date": START, "end_date": END,
              "models": cfg["model"], "timezone": cfg["timezone"]}
    res = []
    for b in range(math.ceil(n / per)):
        s = slice(b * per, (b + 1) * per)
        print(f" - batch {b + 1}/{math.ceil(n / per)}")
        res += openmeteo.fetch(cfg["history_url"], pts["lat"][s], pts["lon"][s], params, len(VARS), n_days,
                               budget, CACHE / f"b{b:03d}.json")
    dates = res[0]["daily"]["time"]
    arr = {v: np.array([[np.nan if x is None else x for x in r["daily"][v]] for r in res], "float32") for v in VARS}
    run = CACHE / "season_run.npz"
    np.savez_compressed(run, dates=np.array(dates), today=np.array(dates[-1]), lon=pts["lon"], lat=pts["lat"],
                        x=pts["x"], y=pts["y"], elev_om=np.array([r.get("elevation", np.nan) for r in res], "float32"),
                        precip=arr["precipitation_sum"], tmean=arr["temperature_2m_mean"],
                        tmin=arr["temperature_2m_min"], tmax=arr["temperature_2m_max"],
                        rh=np.full_like(arr["precipitation_sum"], np.nan), soil=np.full_like(arr["precipitation_sum"], np.nan),
                        model=np.array(cfg["model"]))
    return run


def _get(url, params, cache):
    f = CACHE / "records" / f"{cache}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = requests.get(url, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(r.text)
    return r.json()


def season_records(prof):
    """Dated public Cyprus records of this species in the season: [(date, lat, lon, source)]."""
    names = [n.strip() for n in prof["latin_name"].replace(" group", "").split("/")]
    genus = names[0].split()[0]
    full = [n if " " in n or n == genus else f"{genus} {n}" for n in names]
    out = []
    for nm in full:
        slug = nm.lower().replace(" ", "_")
        try:
            t = _get("https://api.inaturalist.org/v1/taxa", {"q": nm, "per_page": 10}, f"taxa_{slug}")
            hit = [x for x in t["results"] if x["name"] == nm]
            if hit:
                o = _get("https://api.inaturalist.org/v1/observations",
                         {"place_id": INAT_CYPRUS, "taxon_id": hit[0]["id"], "d1": START, "d2": END,
                          "per_page": 200, "quality_grade": "research,needs_id"}, f"inat_{slug}")
                for r in o["results"]:
                    if r.get("observed_on") and r.get("geojson"):
                        lon, lat = r["geojson"]["coordinates"]
                        out.append((r["observed_on"], lat, lon, "iNaturalist"))
            m = _get("https://api.gbif.org/v1/species/match", {"name": nm, "kingdom": "Fungi"}, f"gbif_match_{slug}")
            if m.get("matchType") == "EXACT":
                o = _get("https://api.gbif.org/v1/occurrence/search",
                         {"country": "CY", "taxonKey": m["usageKey"], "eventDate": f"{START},{END}", "limit": 300,
                          "hasCoordinate": "true"}, f"gbif_{m['usageKey']}")
                for r in o["results"]:
                    if r.get("eventDate") and r.get("decimalLatitude") is not None and r.get("datasetKey") != "50c9509d-22c7-4a22-a47d-8c48425ef4a7":
                        out.append((r["eventDate"][:10], r["decimalLatitude"], r["decimalLongitude"], "GBIF"))
        except requests.RequestException as e:
            print(f"   ! records for {nm}: {e}")
    # GBIF also carries iNaturalist research-grade records: keep one per date + place.
    seen, uniq = set(), []
    for d, la, lo, src in sorted(out):
        key = (d, round(la, 2), round(lo, 2))
        if key not in seen:
            seen.add(key)
            uniq.append((d, la, lo, src))
    return uniq


def fill_minmax(run_file):
    """The archive lacks daily min/max for some early days (Sep 2025). Estimate them from the mean
    with each point's usual half-range. Returns (path, number of filled days)."""
    w = dict(np.load(run_file))
    gap = np.isnan(w["tmin"]) | np.isnan(w["tmax"])
    if not gap.any():
        return run_file, 0
    half = np.nanmedian((w["tmax"] - w["tmin"]) / 2, axis=1, keepdims=True)
    w["tmin"] = np.where(gap, w["tmean"] - half, w["tmin"]).astype("float32")
    w["tmax"] = np.where(gap, w["tmean"] + half, w["tmax"]).astype("float32")
    out = run_file.with_name("season_run_filled.npz")
    np.savez_compressed(out, **w)
    return out, int(gap.any(axis=0).sum())


def run(run_file):
    from pyproj import Transformer
    run_file, filled = fill_minmax(run_file)
    E, S = config.load("engine"), config.load("soil")
    profiles = P.load_all()
    hab_grid = _habitat()
    inp = I.build(run_file, hab_grid["land_fraction"] > 0.5)
    hab = habitat_all(inp, profiles, E, S)
    keep = np.nonzero((hab > 0).any(axis=0))[0][::SAMPLE_EVERY]
    inp = I.subset(inp, keep)
    hab = hab[:, keep]
    dates = inp["dates"]
    water = prepare_water(inp, E, S)
    g = habitat_grid()
    to_ll = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True)
    lon, lat = to_ll.transform(g.west + (inp["cols"] + 0.5) * g.res, g.north - (inp["rows"] + 0.5) * g.res)
    from scipy.spatial import cKDTree

    report = {"season": [START, END], "squares_sampled": int(len(keep)), "sample_every": SAMPLE_EVERY,
              "weather_points": int(np.load(run_file)["x"].shape[0]), "dates": dates, "species": {},
              "days_minmax_estimated": filled}
    # Island rain (mean over the weather points), for the "late and cold" check.
    w = np.load(run_file)
    report["island_rain_mm"] = [round(float(v), 1) for v in np.nanmean(w["precip"], axis=0)]
    report["island_tmean_c"] = [round(float(v), 1) for v in np.nanmean(w["tmean"], axis=0)]
    report["bucket_fill_median"] = [round(float(v), 2) for v in np.median(water["fill"], axis=0)]

    for k, prof in enumerate(profiles):
        c = prof["code"]
        m = hab[k] > 0
        if not m.any():
            continue
        r = run_species(prof, I.subset(inp, m), {kk: (v[m] if hasattr(v, "shape") and v.shape[:1] == m.shape else v)
                                                   for kk, v in water.items()}, E, S)
        sc = r["score"] * 100
        st = r["state"]
        recs = season_records(prof)
        tree = cKDTree(np.c_[lon[m], lat[m]])
        rec_out = []
        for d, la, lo, src in recs:
            if d not in dates:
                continue
            t = dates.index(d)
            dist, i = tree.query([lo, la])
            near = tree.query_ball_point([lo, la], 0.05)                  # ~5 km
            rec_out.append({"date": d, "source": src, "km_to_nearest_habitat": round(float(dist) * 100, 1),
                            "score_nearest": int(round(sc[i, t])), "state_nearest": STATE_NAMES[st[i, t]],
                            "best_score_5km": int(round(sc[near, t].max())) if near else None,
                            "open_5km_share": round(float((st[near, t] == OPEN).mean()), 2) if near else None,
                            "island_open_share": round(float((st[:, t] == OPEN).mean()), 3)})
        report["species"][c] = {
            "name": prof["english_name"], "tier": prof["tier"], "squares": int(m.sum()),
            "p90_score": [int(round(v)) for v in np.percentile(sc, 90, axis=0)],
            "median_score": [int(round(v)) for v in np.median(sc, axis=0)],
            "open_share": [round(float(v), 3) for v in (st == OPEN).mean(axis=0)],
            "records": rec_out,
        }
        print(f" - {c}: {m.sum()} squares, {len(rec_out)} dated records in the season")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "backtest_2025-26.json").write_text(json.dumps(report))
    return report


if __name__ == "__main__":
    f = CACHE / "season_run.npz"
    if not f.exists():
        f = fetch_season()
    if "--fetch-only" not in sys.argv:
        run(f)
