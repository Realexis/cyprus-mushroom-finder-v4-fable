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

# Test seasons (audit DIRECTIONS-V4 step 1). The first V4 run used Sep-Feb only; finds go on
# into April (morels, fennel king oyster), so the season now ends 30 April.
SEASONS = {
    "2025-26": ("2025-09-01", "2026-04-30"),
    "2026-autumn": ("2026-09-01", "2026-11-13"),
}
LEGACY_RUN = "2025-26-sepfeb"            # the step 9 file (Sep-Feb, no soil data), kept for comparison
CACHE = config.RAW / "weather" / "backtest"
OUT = config.PROCESSED / "backtest"
VARS = ["precipitation_sum", "temperature_2m_mean", "temperature_2m_min", "temperature_2m_max"]
HOURLY = ["soil_temperature_0_to_7cm", "soil_moisture_0_to_7cm"]   # daily means are made from these
SAMPLE_EVERY = 4                                  # every 4th habitat square (keeps memory small)
HEADERS = {"User-Agent": "cyprus-mushroom-finder/0.1 (non-commercial, static site)"}
INAT_CYPRUS = "10289,96773"
NEAR_M = 5000                                     # "within 5 km"


def season_points():
    g = habitat_grid()
    hab = _habitat()
    k = int(config.load("weather")["soil_climatology"]["block_km"] * 1000 / g.res)
    return _to_table(block_points(hab["land_fraction"] > 0.5, k), g)


def season_cost(season):
    start, end = SEASONS[season]
    n_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    return len(season_points()["lat"]) * openmeteo.call_cost(1, len(VARS) + len(HOURLY), n_days), n_days


def fetch_season(season):
    """Daily weather + daily-mean soil temperature and moisture on the 9 km grid. Cached per batch."""
    from .weather.fetch import _daily_mean_from_hourly
    start, end = SEASONS[season]
    wcfg = config.load("weather")
    cfg, caps = wcfg["open_meteo"], wcfg["budget"]
    pts = season_points()
    n = len(pts["lat"])
    total, n_days = season_cost(season)
    per_loc = total / n
    print(f"{season}: {n} points x {n_days} days: ~{total:,.0f} calls")
    budget = openmeteo.Budget(caps)
    per = max(1, int(caps["per_minute"] * 0.8 // per_loc))
    params = {"daily": ",".join(VARS), "hourly": ",".join(HOURLY), "start_date": start, "end_date": end,
              "models": cfg["model"], "timezone": cfg["timezone"]}
    res = []
    for b in range(math.ceil(n / per)):
        s = slice(b * per, (b + 1) * per)
        print(f" - batch {b + 1}/{math.ceil(n / per)}")
        res += openmeteo.fetch(cfg["history_url"], pts["lat"][s], pts["lon"][s], params, len(VARS) + len(HOURLY),
                               n_days, budget, CACHE / season / f"b{b:03d}.json")
    dates = res[0]["daily"]["time"]
    arr = {v: np.array([[np.nan if x is None else x for x in r["daily"][v]] for r in res], "float32") for v in VARS}
    hourly = {}
    for v in HOURLY:
        rows = []
        for r in res:
            dm = _daily_mean_from_hourly(r["hourly"]["time"], r["hourly"][v])
            rows.append([dm.get(d, np.nan) for d in dates])
        hourly[v] = np.array(rows, "float32")
    run = CACHE / season / "season_run.npz"
    np.savez_compressed(run, dates=np.array(dates), today=np.array(dates[-1]), lon=pts["lon"], lat=pts["lat"],
                        x=pts["x"], y=pts["y"], elev_om=np.array([r.get("elevation", np.nan) for r in res], "float32"),
                        precip=arr["precipitation_sum"], tmean=arr["temperature_2m_mean"],
                        tmin=arr["temperature_2m_min"], tmax=arr["temperature_2m_max"],
                        rh=np.full_like(arr["precipitation_sum"], np.nan),
                        soil=hourly["soil_moisture_0_to_7cm"], tsoil_om=hourly["soil_temperature_0_to_7cm"],
                        model=np.array(cfg["model"]))
    return run


def run_file_for(season):
    if season == LEGACY_RUN:
        return CACHE / "season_run.npz"
    return CACHE / season / "season_run.npz"


def _get(url, params, cache):
    f = CACHE / "records" / f"{cache}.json"
    if f.exists():
        return json.loads(f.read_text())
    r = requests.get(url, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(r.text)
    return r.json()


# ------------------------------------------------------------------ dated public records
# Cyprus observers rarely use exact species names (audit GAPS B12), so some profiles search a
# genus or a group and keep the records that fit. "weak" = genus only, reported apart.
# Profiles not listed here search their own latin_name, as before.
RECORD_RULES = {
    "slu": {"search": [("Suillus", "genus")]},                          # 0 S. luteus, 5 S. collinitus in Cyprus
    "lde": {"search": [("Lactarius", "genus")],                         # Cistus milk caps are not pine partners
            "drop": ["Lactarius tesquorum", "Lactarius cistophilus", "Lactarius sanguifluus"]},
    "mor": {"search": [("Morchella", "genus")]},
    "pfe": {"search": [("Pleurotus eryngii", "species")]},
    "cco": {"search": [("Coprinus comatus", "species")]},
    "aca": {"search": [("Agaricus", "genus")], "weak": True},           # genus only: many Agaricus species
    "rde": {"search": [("Russula", "genus")],                          # R. delica or subgenus Brevipes;
            "keep": ["Russula delica"], "keep_ids": [1167951],             # 1167951 = iNat subgenus Brevipes
            "weak_rank": "genus"},                                          # genus-only Russula = weak
}
GBIF_INAT_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"   # iNaturalist research grade, already counted


def _slug(name):
    return name.lower().replace(" ", "_")


def _inat(name, rank, d1, d2):
    """iNaturalist records in Cyprus (research grade + needs ID) of this taxon and everything under it."""
    t = _get("https://api.inaturalist.org/v1/taxa", {"q": name, "rank": rank, "per_page": 10}, f"taxa_{rank}_{_slug(name)}")
    hit = [x for x in t["results"] if x["name"] == name]
    if not hit:
        return []
    out, page = [], 1
    while True:
        o = _get("https://api.inaturalist.org/v1/observations",
                 {"place_id": INAT_CYPRUS, "taxon_id": hit[0]["id"], "d1": d1, "d2": d2, "per_page": 200,
                  "page": page, "quality_grade": "research,needs_id"}, f"inat_{_slug(name)}_{d1}_{d2}_p{page}")
        for r in o["results"]:
            if r.get("observed_on") and r.get("geojson") and r.get("taxon"):
                lon, lat = r["geojson"]["coordinates"]
                tx = r["taxon"]
                out.append({"date": r["observed_on"], "lat": lat, "lon": lon, "taxon": tx["name"],
                            "rank": tx["rank"], "ancestor_ids": tx.get("ancestor_ids") or [tx["id"]],
                            "source": "iNaturalist"})
        if page * 200 >= o.get("total_results", 0):
            return out
        page += 1


def _gbif(name, rank, d1, d2):
    m = _get("https://api.gbif.org/v1/species/match", {"name": name, "rank": rank.upper(), "kingdom": "Fungi"},
             f"gbif_match_{rank}_{_slug(name)}")
    if m.get("matchType") != "EXACT":
        return []
    o = _get("https://api.gbif.org/v1/occurrence/search",
             {"country": "CY", "taxonKey": m["usageKey"], "eventDate": f"{d1},{d2}", "limit": 300,
              "hasCoordinate": "true"}, f"gbif_{m['usageKey']}_{d1}_{d2}")
    out = []
    for r in o["results"]:
        if r.get("eventDate") and r.get("decimalLatitude") is not None and r.get("datasetKey") != GBIF_INAT_DATASET:
            tx = r.get("species") or r.get("genus") or r.get("scientificName", "")
            out.append({"date": r["eventDate"][:10], "lat": r["decimalLatitude"], "lon": r["decimalLongitude"],
                        "taxon": tx, "rank": (r.get("taxonRank") or "").lower(), "ancestor_ids": [],
                        "source": "GBIF"})
    return out


def classify(rec, rule):
    """'strong', 'weak' or None (record does not belong to this profile)."""
    if any(rec["taxon"].startswith(d) for d in rule.get("drop", [])):
        return None
    keep, ids = rule.get("keep"), rule.get("keep_ids", [])
    if keep or ids:
        if any(rec["taxon"].startswith(k) for k in keep or []) or set(ids) & set(rec.get("ancestor_ids", [])):
            return "weak" if rule.get("weak") else "strong"
        if rec["rank"] == rule.get("weak_rank"):
            return "weak"
        return None
    return "weak" if rule.get("weak") else "strong"


def find_events(recs):
    """Same date and same place (about 1 km) = one find event. recs: dicts with date, lat, lon."""
    ev = {}
    for r in sorted(recs, key=lambda r: (r["date"], r["source"] != "iNaturalist")):
        key = (r["date"], round(r["lat"], 2), round(r["lon"], 2), r["strength"])
        e = ev.setdefault(key, {**r, "records": 0, "taxa": set()})
        e["records"] += 1
        e["taxa"].add(r["taxon"])
    out = []
    for e in ev.values():
        e = dict(e)
        e["taxa"] = sorted(e["taxa"])
        for k in ("ancestor_ids", "rank", "taxon"):
            e.pop(k, None)
        out.append(e)
    return sorted(out, key=lambda e: (e["date"], e["lat"]))


def season_records(prof, d1, d2):
    """Dated public Cyprus find events of this profile between d1 and d2 (ISO dates)."""
    rule = RECORD_RULES.get(prof["code"])
    if rule is None:
        names = [n.strip() for n in prof["latin_name"].replace(" group", "").split("/")]
        genus = names[0].split()[0]
        full = [n if " " in n or n == genus else f"{genus} {n}" for n in names]
        rule = {"search": [(n, "species" if " " in n else "genus") for n in full]}
    recs = []
    for nm, rank in rule["search"]:
        try:
            recs += _inat(nm, rank, d1, d2) + _gbif(nm, rank, d1, d2)
        except requests.RequestException as e:
            print(f"   ! records for {nm}: {e}")
    out = []
    for r in recs:
        s = classify(r, rule)
        if s:
            out.append({**r, "strength": s})
    return find_events(out)


def nearest_open_offset(open_any, t):
    """Days from day t to the nearest day with a window open: 0 = open that day,
    -N = the last window closed N days before, +N = the next one opened N days later. None = never."""
    idx = np.nonzero(open_any)[0]
    if not len(idx):
        return None
    j = idx[np.argmin(np.abs(idx - t))]
    return int(j - t)


def fair_score(events):
    """Hit rate (window open within 5 km on the find day) beside the base rate
    (share of all season days with a window open there). The gap is the real result."""
    ev = [e for e in events if e.get("open_5km") is not None]
    if not ev:
        return {"events": 0}
    hit = float(np.mean([e["open_5km"] for e in ev]))
    base = float(np.mean([e["open_days_share_5km"] for e in ev]))
    return {"events": len(ev), "hit_rate": round(hit, 2), "base_rate": round(base, 2), "gap": round(hit - base, 2)}


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


def run(run_file, season, label=None):
    """Run every profile over the season and score it against the dated find events."""
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
    d1, d2 = dates[0], dates[-1]
    water = prepare_water(inp, E, S)
    g = habitat_grid()
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    to_grid = Transformer.from_crs("EPSG:4326", g.crs, always_xy=True)
    sx = g.west + (inp["cols"] + 0.5) * g.res
    sy = g.north - (inp["rows"] + 0.5) * g.res

    report = {"season": season, "label": label or season, "dates_run": [d1, d2],
              "squares_sampled": int(len(keep)), "sample_every": SAMPLE_EVERY,
              "weather_points": int(np.load(run_file)["x"].shape[0]), "dates": dates, "species": {},
              "days_minmax_estimated": filled}
    w = np.load(run_file)
    report["island_rain_mm"] = [round(float(v), 1) for v in np.nanmean(w["precip"], axis=0)]
    report["island_tmean_c"] = [round(float(v), 1) for v in np.nanmean(w["tmean"], axis=0)]
    report["bucket_fill_median"] = [round(float(v), 2) for v in np.median(water["fill"], axis=0)]

    all_strong, all_weak = [], []
    for k, prof in enumerate(profiles):
        c = prof["code"]
        m = hab[k] > 0
        if not m.any():
            continue
        r = run_species(prof, I.subset(inp, m), {kk: (v[m] if hasattr(v, "shape") and v.shape[:1] == m.shape else v)
                                                   for kk, v in water.items()}, E, S)
        sc = r["score"] * 100
        st = r["state"]
        is_open = st == OPEN
        tree = cKDTree(np.c_[sx[m], sy[m]])
        events = []
        for e in season_records(prof, d1, d2):
            if e["date"] not in dates:
                continue
            t = dates.index(e["date"])
            ex, ey = to_grid.transform(e["lon"], e["lat"])
            dist, i = tree.query([ex, ey])
            near = tree.query_ball_point([ex, ey], NEAR_M)
            row = {"date": e["date"], "lat": round(e["lat"], 3), "lon": round(e["lon"], 3), "source": e["source"],
                   "records": e["records"], "taxa": e["taxa"], "strength": e["strength"],
                   "km_to_nearest_habitat": round(float(dist) / 1000, 1),
                   "score_nearest": int(round(sc[i, t])), "state_nearest": STATE_NAMES[st[i, t]],
                   "open_offset_nearest": nearest_open_offset(is_open[i], t)}
            if near:
                open_any = is_open[near].any(axis=0)
                row.update({"best_score_5km": int(round(sc[near, t].max())), "open_5km": bool(open_any[t]),
                            "open_share_5km": round(float(is_open[near, t].mean()), 2),
                            "open_days_share_5km": round(float(open_any.mean()), 3),
                            "open_offset_5km": nearest_open_offset(open_any, t)})
            else:
                row.update({"best_score_5km": None, "open_5km": None, "open_days_share_5km": None,
                            "open_offset_5km": None})
            events.append(row)
        strong = [e for e in events if e["strength"] == "strong"]
        weak = [e for e in events if e["strength"] == "weak"]
        all_strong += strong
        all_weak += weak
        report["species"][c] = {
            "name": prof["english_name"], "tier": prof["tier"], "squares": int(m.sum()),
            "p90_score": [int(round(v)) for v in np.percentile(sc, 90, axis=0)],
            "median_score": [int(round(v)) for v in np.median(sc, axis=0)],
            "open_share": [round(float(v), 3) for v in is_open.mean(axis=0)],
            "events": events, "fair": fair_score(strong), "fair_weak": fair_score(weak),
        }
        print(f" - {c}: {m.sum()} squares, {len(strong)} find events (+{len(weak)} genus-only)")
    report["fair"] = fair_score(all_strong)
    report["fair_weak"] = fair_score(all_weak)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"backtest_{label or season}.json"
    out.write_text(json.dumps(report))
    print_summary(report)
    return report


def print_summary(rep):
    print(f"\n{rep['label']}: {rep['dates_run'][0]} to {rep['dates_run'][1]}")
    f = rep["fair"]
    if f.get("events"):
        print(f"ALL find events: {f['events']}  hit {f['hit_rate']:.0%}  base {f['base_rate']:.0%}  gap {f['gap']:+.0%}")
    fw = rep["fair_weak"]
    if fw.get("events"):
        print(f"genus-only (weak): {fw['events']}  hit {fw['hit_rate']:.0%}  base {fw['base_rate']:.0%}  gap {fw['gap']:+.0%}")
    for c, v in rep["species"].items():
        for e in v["events"]:
            print(f"  {e['date']} {c} {e['strength'][0]} nearest {e['state_nearest']:<10} {e['score_nearest']:>3}"
                  f"  5km best {e['best_score_5km']}  open {e['open_5km']}  offset {e['open_offset_5km']}"
                  f"  ({e['km_to_nearest_habitat']} km)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-26", choices=[*SEASONS, LEGACY_RUN])
    ap.add_argument("--label", default=None, help="name of the output file (default: the season)")
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--cost", action="store_true", help="print the Open-Meteo cost and stop")
    a = ap.parse_args()
    if a.cost:
        print(f"{a.season}: ~{season_cost(a.season)[0]:,.0f} calls")
        sys.exit()
    f = run_file_for(a.season)
    if not f.exists():
        f = fetch_season(a.season)
    if not a.fetch_only:
        run(f, a.season, a.label)
