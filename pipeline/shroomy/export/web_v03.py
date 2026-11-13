"""v0.3 map export: the species engine (docs/methodology-v0.3.md). Used by web.build when
species/*.yaml profiles exist. Everything here is public: growing conditions only.

web/public/data/
  cells.pmtiles            250 m squares with any species habitat: shape + fixed facts (no scores)
  sp_<key>.bin             scores per square per day for one species, or the general maps
                           "key" (key species) and "all" (key + more). Small: loaded to colour the map.
  sp_<key>_info.bin        the parts and plain numbers behind those scores (loaded on a tap)
  cells_info.bin           nearest track and road per square; cells_road.bin = Drive there pins
  hexes.geojson, spots.json ~2 km zones (key general map); summary.json; meta.json; rain; reserves

Binary layouts (little-endian):
  sp_<key>.bin       uint32 n, uint32 days, uint32 idx[n] (square "i", ascending), uint8 score[n*days] (0-100)
  sp_<key>_info.bin  uint32 n, days, nparts, ninputs; uint8 parts[n*days*nparts] (x100);
                     pad to 2 bytes; int16 inputs[n*days*ninputs] (x10). Same square order as sp_<key>.bin.

Run:  uv run python -m shroomy.export.web
"""
import json
import shutil
from datetime import date, datetime, timezone

import h3
import numpy as np
from pyproj import Transformer

from .. import config
from ..engine import daily as D
from ..engine.cycle import STATE_NAMES
from ..engine.profile import load_all
from ..grid import habitat_grid
from ..score.today import load_habitat
from . import roads, summary
from .web import N_DAYS, PUBLIC, STATIC, _nanmean, _write_geojson, confidence, write_pmtiles

GENERAL_INPUTS = D.INPUTS + ["best"]          # general maps also say which species is best


def _mode(a):
    """Most common whole value per column (states and day counts in a zone)."""
    a = np.asarray(a).astype(int)
    off = a.min()
    return np.array([np.bincount(col - off).argmax() + off for col in a.T])


def write_scores(path, idx, score):
    n = len(idx)
    with open(path, "wb") as f:
        f.write(np.array([n, N_DAYS], "<u4").tobytes())
        f.write(np.asarray(idx, "<u4").tobytes())
        f.write(np.asarray(score, "u1").reshape(n, N_DAYS).tobytes())


def write_info(path, parts, inputs):
    n, d, npart = parts.shape
    ninp = inputs.shape[2]
    body = np.asarray(parts, "u1").tobytes()
    with open(path, "wb") as f:
        f.write(np.array([n, d, npart, ninp], "<u4").tobytes())
        f.write(body)
        if len(body) % 2:
            f.write(b"\0")
        f.write(np.asarray(inputs, "<i2").tobytes())


def rain_since(run_file, today):
    """Island-average rain from the engine run's first day to today (a plain fact for the cards,
    audit step 9). Not part of any score."""
    w = np.load(run_file)
    d = [str(x) for x in w["dates"]]
    t = d.index(today.isoformat())
    mm = float(np.nanmean(np.nansum(w["precip"][:, : t + 1], axis=1)))
    return {"from": d[0], "to": d[t], "mm": int(round(mm)), "from_1_sep": d[0][5:] == "09-01"}


# General score files: this value = no species with habitat here is in season that day (round 2, fix 2).
NO_SPECIES_IN_SEASON = 255


def build(run, engine_run=None):
    """engine_run: the longer season run file for the engine's memory (audit step 4); default `run`."""
    w = np.load(run)
    today = date.fromisoformat(str(w["today"]))
    dates = [str(d) for d in w["dates"]]
    t0 = dates.index(today.isoformat())
    S = config.load("scoring")
    pv = S["public_view"]
    min_cells = pv["min_open_forest_cells"]
    hab = load_habitat()
    g = habitat_grid()
    to_ll = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True)
    rd = roads.load()
    PUBLIC.mkdir(parents=True, exist_ok=True)
    for old in list(PUBLIC.glob("sp_*.bin")) + list(PUBLIC.glob("cells_sp_*.bin")):
        old.unlink()

    profiles = load_all()
    E = config.load("engine")
    print(f"Running the species engine ({len(profiles)} species)")
    eng = D.run(engine_run or run, hab["land_fraction"] > 0.5, profiles)
    codes = eng["codes"]
    rows, cols = eng["rows"], eng["cols"]
    n = len(rows)
    sq = np.arange(n)                                               # square index "i" in the tiles

    # ---------------------------------------------------------- scores + details per species and general map
    groups = {c: eng["habitat"][k] > 0 for k, c in enumerate(codes)}
    sets = {c: (groups[c], eng["score"][c], eng["parts"][c], eng["inputs"][c]) for c in codes}
    for name, ge in eng["general"].items():
        best = (ge["best"].astype("int16") * 10)[:, :, None]
        sc = np.where(ge["in_season"], ge["score"], NO_SPECIES_IN_SEASON).astype("uint8")
        sets[name] = (ge["habitat"] > 0, sc, ge["parts"], np.concatenate([ge["inputs"], best], axis=2))
    for name, (m, sc, pa, inp) in sets.items():
        write_scores(PUBLIC / f"sp_{name}.bin", sq[m], sc[m])
        write_info(PUBLIC / f"sp_{name}_info.bin", pa[m], inp[m])
    print(f" - scores for {len(codes)} species + general maps (key, all)")

    # ---------------------------------------------------------- ~2 km zones (key general map)
    cx = g.west + (cols + 0.5) * g.res
    cy = g.north - (rows + 0.5) * g.res
    lon, lat = to_ll.transform(cx, cy)
    tree = hab["likely_tree"][rows, cols].astype(int)
    elev = hab["elevation_m"][rows, cols]
    gk = eng["general"]["key"]
    gen = gk["habitat"] > 0
    score = np.where(gen[:, None] & gk["in_season"], gk["score"].astype(float), np.nan)
    fac = gk["parts"].astype(float) / 100
    inp = gk["inputs"].astype(float) / 10
    hexes = np.array([h3.latlng_to_cell(la, lo, pv["h3_resolution"]) for la, lo in zip(lat, lon)])
    order = np.argsort(hexes, kind="stable")
    uh, starts = np.unique(hexes[order], return_index=True)
    places = summary.load_places()
    feats, zones, spots = [], [], []
    zone_of = np.full(n, -1, "int32")
    for hx, m in zip(uh, np.split(order, starts[1:])):
        mg = m[gen[m]]
        has_gen = len(mg) >= min_cells
        sp_cells = {c: m[groups[c][m]] for c in codes}
        sp_cells = {c: v for c, v in sp_cells.items() if len(v) >= min_cells}
        if not has_gen and not sp_cells:
            continue
        ring = [[lo, la] for la, lo in h3.cell_to_boundary(hx)]
        ring.append(ring[0])
        props = {"h": len(spots)}
        zone_of[m] = len(spots)
        gen_score = _nanmean(score[mg]) if has_gen else None           # NaN on days with no species in season
        # Forecast confidence of the zone (spec 3.7): its mean score with vs without forecast rain.
        conf = (D.confidence(D.rain_dependence(gen_score, gk["dry"][mg].astype(float).mean(axis=0)), E["confidence"])
                if has_gen else None)
        if has_gen:
            props.update({f"s{i}": int(round(v)) for i, v in enumerate(gen_score) if np.isfinite(v)})
        sp_mean = {c: eng["score"][c][v].astype(float).mean(axis=0) for c, v in sp_cells.items()}
        sp_conf = {c: D.confidence(D.rain_dependence(sp_mean[c], eng["dry"][c][v].astype(float).mean(axis=0)),
                                   E["confidence"]) for c, v in sp_cells.items()}
        feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}})
        sel = mg if has_gen else m
        fm = {k: _nanmean(fac[sel, :, j]) for j, k in enumerate(D.PARTS)}
        im = {k: (_mode(inp[sel, :, j]) if k in ("state", "left_days") else _nanmean(inp[sel, :, j]))
              for j, k in enumerate(D.INPUTS)}
        clat, clon = h3.cell_to_latlng(hx)
        counts = np.bincount(tree[m], minlength=6)[1:5]
        alt = (float(np.nanmin(elev[m])), float(np.nanmax(elev[m])))
        spots.append({
            "where": summary.near(clat, clon, places), "alt": [int(alt[0]), int(alt[1])],
            "trees": {str(i + 1): round(float(k) / len(m), 2) for i, k in enumerate(counts) if k},
            "f": [[int(round(float(np.nan_to_num(fm[k][d])) * 100)) for k in D.PARTS] for d in range(N_DAYS)],
            "in": [[round(float(np.nan_to_num(im[k][d])), 1) for k in D.INPUTS] for d in range(N_DAYS)],
            "road": rd.describe(float(cx[m].mean()), float(cy[m].mean())) if rd else None,
        })
        zones.append({"hex": hx, "lat": clat, "lon": clon, "score": gen_score, "species": sp_mean,
                      "conf": conf, "species_conf": sp_conf,
                      "factors": fm, "inputs": im, "clock": np.zeros(N_DAYS, int),
                      "trees": np.bincount(tree[m], minlength=6)[1:] / len(m), "alt": alt,
                      "where": spots[-1]["where"], "spot": len(spots) - 1})
    _write_geojson(PUBLIC / "hexes.geojson", feats)
    (PUBLIC / "spots.json").write_text(json.dumps({"factors": D.PARTS, "inputs": D.INPUTS, "spots": spots},
                                                  separators=(",", ":"), ensure_ascii=False))
    print(f" - {len(feats)} zones ({sum(z['score'] is not None for z in zones)} on the key-species map)")

    # ---------------------------------------------------------- rain squares + reserves
    half = config.load("region")["grids"]["weather_m"] / 2
    p = w["precip"]
    rfeats = []
    for i in range(len(w["x"])):
        x, y = float(w["x"][i]), float(w["y"][i])
        xs, ys = to_ll.transform([x - half, x + half, x + half, x - half, x - half],
                                 [y - half, y - half, y + half, y + half, y - half])
        rfeats.append({"type": "Feature", "properties": {
            "r7": float(np.nansum(p[i, t0 - 6: t0 + 1])), "r30": float(np.nansum(p[i, t0 - 29: t0 + 1])),
            "d": [round(float(v), 1) for v in p[i, t0 - 29: t0 + N_DAYS]]},
            "geometry": {"type": "Polygon", "coordinates": [list(zip(xs, ys))]}})
    _write_geojson(PUBLIC / "rain.geojson", rfeats, ndigits=4)
    shutil.copy(STATIC / "reserves.geojson", PUBLIC / "reserves.geojson")

    # ---------------------------------------------------------- meta + summary
    sources = config.load("sources")
    mc = S["score"]["mushroom_clock"]
    day_info = [{"offset": i, "date": dates[t0 + i], "confidence": confidence(i)} for i in range(N_DAYS)]
    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "weather_run": today.isoformat(), "model": str(w["model"]),
        "days": day_info, "rain_days": dates[t0 - 29: t0 + N_DAYS],
        "public_hexagon_resolution": pv["h3_resolution"],
        "clock": {"opens": mc["window_opens_days_after_pulse"], "closes": mc["window_closes_days_after_pulse"],
                  "soak_mm": S["score"]["rain_pulse"]["soaking_event_mm"]},
        "weights": {}, "season_share": 0, "general_map_trees": S["score"]["general_map_trees"],
        "engine": {"parts": D.PARTS, "inputs": D.INPUTS, "general_inputs": GENERAL_INPUTS, "codes": codes,
                   "general": {k: v["codes"] for k, v in eng["general"].items()},
                   "species": eng["profiles"], "states": STATE_NAMES,
                   "confidence": {k: E["confidence"][k] for k in ("sure_below", "likely_below")}},
        "credits": [{"name": v["name"], "credit": v["credit"], "licence": v["licence"],
                     "status": v["licence_status"], "use": v.get("use", "")}
                    for v in sources.values() if isinstance(v, dict) and "credit" in v],
        "safety": "Conditions only. Never eat a wild mushroom based on this map, an app or an AI.",
    }
    meta["rain_since"] = rain_since(engine_run or run, today)
    (PUBLIC / "meta.json").write_text(json.dumps(meta, indent=1))
    specs = [{"code": c, "latin": q["latin_name"], "common": q["english_name"], "months": list(range(1, 13)),
              "season_text": q["season_text"], "tier": q["tier"]} for c, q in eng["profiles"].items()]
    summ = summary.build(zones, day_info, meta, specs, engine=True)
    (PUBLIC / "summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False))
    print(f" - summary.json: top {len(summ['days'][0]['top_zones'])} zones per day + {len(specs)} species")

    export_cells(eng, hab, g, to_ll, rd, zone_of)
    from . import hotspots
    hotspots.build(summ, g)


def export_cells(eng, hab, g, to_ll, rd, zone_of):
    """Every square with habitat -> PMTiles (shape + fixed facts) + road details (public)."""
    import rasterio
    rows, cols = eng["rows"], eng["cols"]
    n = len(rows)
    x = g.west + (cols + 0.5) * g.res
    y = g.north - (rows + 0.5) * g.res
    tree = hab["likely_tree"][rows, cols].astype(int)
    band = hab["altitude_band"][rows, cols].astype(int)

    soil = {}
    v03 = config.PROCESSED / "habitat_v03_250m.tif"
    if v03.exists():
        with rasterio.open(v03) as src:
            b = {src.descriptions[i]: src.read(i + 1) for i in range(src.count)}
        awc = b["awc_mm"][rows, cols]
        forest = tree > 0
        lo, hi = np.nanpercentile(awc[forest], [33.3, 66.7])          # "holds water" vs Cyprus forests
        rel_band = (b["awc_q95_mm"] - b["awc_q05_mm"])[rows, cols] / np.where(awc > 0, awc, np.nan)
        soil = {"awc": awc, "hold": np.where(awc <= lo, 1, np.where(awc <= hi, 2, 3)),
                "ph": b["ph"][rows, cols], "tc": b["tree_cover_pct"][rows, cols],
                "unsure": (rel_band > config.load("soil")["soil_effect"]["neutral_at_rel_band"]) | ~np.isfinite(rel_band)}

    info = np.full((n, 2), -1, "int16")                              # nearest track, road (m)
    if rd:
        dt, dr, _ = rd.distances(x, y)
        info[:, 0] = np.clip(np.nan_to_num(dt, nan=-1), -1, 32000)
        info[:, 1] = np.clip(np.nan_to_num(dr, nan=-1), -1, 32000)
    (PUBLIC / "cells_info.bin").write_bytes(info.astype("<i2").tobytes())
    clo, cla = to_ll.transform(x, y)
    pins = roads.square_pins(cla, clo, hab["reserve_id"][rows, cols])
    (PUBLIC / "cells_road.bin").write_bytes(pins.astype("<f4").tobytes())
    (PUBLIC / "cells_info.json").write_text(json.dumps({
        "cells": n, "days": N_DAYS, "factors": [], "inputs": [],
        "layout": "int16 little-endian; per square: track_m, road_m; -1 = none. Scores: sp_<key>.bin (see web_v03.py)",
        "road_layout": "cells_road.bin: float32 little-endian; per square: lat, lon of its centre (Drive there pin); NaN = in/touching a nature reserve"}))

    feats = []
    for k, (r, c) in enumerate(zip(rows, cols)):
        x0 = g.west + c * g.res; y1 = g.north - r * g.res
        xs, ys = to_ll.transform([x0, x0 + g.res, x0 + g.res, x0, x0], [y1, y1, y1 - g.res, y1 - g.res, y1])
        props = {"i": k, "tree": int(tree[k]), "band": int(band[k]), "closed": 0,
                 "elev": int(round(float(np.nan_to_num(hab["elevation_m"][r, c]))))}
        if zone_of[k] >= 0:
            props["h"] = int(zone_of[k])
        if soil and np.isfinite(soil["awc"][k]):
            props.update({"awc": int(round(float(soil["awc"][k]))), "hold": int(soil["hold"][k]),
                          "ph": int(round(float(soil["ph"][k]) * 10)), "su": int(bool(soil["unsure"][k]))})
        if soil and np.isfinite(soil["tc"][k]):
            props["tc"] = int(round(float(soil["tc"][k])))
        feats.append({"type": "Feature", "id": k, "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": [list(zip(xs, ys))]}})
    gj = PUBLIC / "cells.geojson"
    _write_geojson(gj, feats)
    write_pmtiles(gj, PUBLIC / "cells.pmtiles", "cells", 6, 13)
    gj.unlink()
    print(f" - {n} public 250 m squares (shape + facts)")
