"""Export map data for the website (all public, deployed daily):

web/public/data/  hexagons + zone details (spots.json), 250 m forest squares (cells.pmtiles)
                  + their details (cells_info.bin, cells_road.bin), 50 m hotspot terrain for the
                  top zones (hotspots.pmtiles, when the terrain inputs exist), rain squares,
                  reserves, meta, summary.json.

User decision 2026-11-12: the public site shows the 250 m squares (conditions only), like the
former private view. It overrides the brief's "~2 km hexagons only" rule. Finds (Phase 6) stay private.

Run:  uv run python -m shroomy.export.web          (--public is accepted and ignored, for the daily robot)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import date, datetime, timezone

import h3
import numpy as np
import rasterio
from pyproj import Transformer
from scipy.spatial import cKDTree

from .. import config
from ..grid import habitat_grid
from ..score import clock
from ..score import species as SP
from ..score.factors import FACTORS
from ..score.today import latest_run, load_habitat, score_day
from . import roads, summary

PUBLIC = config.ROOT / "web" / "public" / "data"
STATIC = config.DATA / "static"
N_DAYS = 8
INPUTS = ["rain_30d_mm", "pulse_mm", "t7_mean_c", "soil_percentile", "frost_days"]


def confidence(offset: int) -> str:
    c = config.load("scoring")["score"]["forecast_confidence"]
    if offset <= c["high_max_day"]:
        return "high"
    if offset <= c["medium_max_day"]:
        return "medium"
    return "low"


def _read(tif):
    with rasterio.open(tif) as src:
        return {src.descriptions[i]: src.read(i + 1) for i in range(src.count)}


def _rnd(o, nd):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, (list, tuple)):
        return [_rnd(x, nd) for x in o]
    if isinstance(o, dict):
        return {k: _rnd(v, nd) for k, v in o.items()}
    return o


def _write_geojson(path, features, ndigits=5):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": _rnd(features, ndigits)},
                               separators=(",", ":")))


def write_pmtiles(geojson: Path, out: Path, layer: str, minzoom: int, maxzoom: int):
    """GeoJSON -> vector PMTiles. tippecanoe when installed (your Mac), else GDAL's PMTiles
    driver bundled with pyogrio (the daily robot has no tippecanoe)."""
    if shutil.which("tippecanoe"):
        subprocess.run(["tippecanoe", "-q", "-f", "-o", str(out), "-l", layer, f"-Z{minzoom}", f"-z{maxzoom}",
                        "--no-feature-limit", "--no-tile-size-limit", "--simplify-only-low-zooms",
                        "--detect-shared-borders", str(geojson)], check=True)
        return
    import pyogrio
    out.unlink(missing_ok=True)
    df = pyogrio.read_dataframe(geojson)
    pyogrio.write_dataframe(df, out, driver="PMTiles", layer=layer,
                            dataset_options={"MINZOOM": str(minzoom), "MAXZOOM": str(maxzoom),
                                             "MAX_SIZE": "2000000", "MAX_FEATURES": "500000"})


def _nanmean(a, axis=0):
    with np.errstate(invalid="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(a, axis=axis)


def clock_days(w, t0):
    """Days since the last soaking rain at each weather point, for day offsets 0..7."""
    S = config.load("scoring")["score"]
    rp, mc = S["rain_pulse"], S["mushroom_clock"]
    return np.stack([clock.days_since_soak(w["precip"], t0 + k, rp["window_days"],
                                           rp["soaking_event_mm"], mc["wet_day_mm"])
                     for k in range(N_DAYS)], axis=1)                      # (points, 8)


def species_scores(base, months, specs, share):
    """Per-cell species score for each day (habitat mask applied by the caller)."""
    return {s["code"]: (base + share) * np.array([SP.in_season(m, s) for m in months], float)[None, :]
            for s in specs}


def build(run, private=True, engine_run=None):            # `private` is kept for old callers; everything is public now
    # v0.3: when species profiles exist (species/*.yaml), the map shows the species engine.
    from ..engine.profile import load_all
    if load_all():
        from . import web_v03
        return web_v03.build(run, engine_run)
    w = np.load(run)
    today = date.fromisoformat(str(w["today"]))
    dates = [str(d) for d in w["dates"]]
    t0 = dates.index(today.isoformat())
    S = config.load("scoring")
    pv = S["public_view"]
    W = S["score"]["weights"]
    specs = config.load("species")["species"]
    months = [date.fromisoformat(dates[t0 + k]).month for k in range(N_DAYS)]
    min_cells = pv["min_open_forest_cells"]

    print("Scoring 8 days")
    days = [_read(score_day(run, off)) for off in range(N_DAYS)]
    hab = load_habitat()
    g = habitat_grid()
    to_ll = Transformer.from_crs(g.crs, "EPSG:4326", always_xy=True)
    clk_pt = clock_days(w, t0)
    pt_tree = cKDTree(np.c_[w["x"], w["y"]])
    rd = roads.load()

    PUBLIC.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------- every open forest cell
    rows, cols = np.nonzero(hab["habitat_filter"] > 0)
    cx = g.west + (cols + 0.5) * g.res
    cy = g.north - (rows + 0.5) * g.res
    lon, lat = to_ll.transform(cx, cy)
    tree = hab["likely_tree"][rows, cols].astype(int)
    band = hab["altitude_band"][rows, cols].astype(int)
    elev = hab["elevation_m"][rows, cols]
    gen = np.isin(tree, S["score"]["general_map_trees"])                    # [S7]

    score = np.stack([d["score"][rows, cols] for d in days], axis=1)       # NaN off the general map
    fac = {k: np.stack([d[f"f_{k}"][rows, cols] for d in days], axis=1) for k in FACTORS}
    inp = {k: np.stack([d[k][rows, cols] for d in days], axis=1) for k in INPUTS}
    base = np.stack([SP.base_score({k: fac[k][:, i] for k in FACTORS}, W) for i in range(N_DAYS)], axis=1)
    share = SP.season_share(W)
    sp_mask = {s["code"]: SP.species_habitat(np.ones_like(tree), tree, band, s) for s in specs}
    sp_score = species_scores(base, months, specs, share)

    # ---------------------------------------------------------- hexagons (public)
    hexes = np.array([h3.latlng_to_cell(la, lo, pv["h3_resolution"]) for la, lo in zip(lat, lon)])
    order = np.argsort(hexes, kind="stable")
    uh, starts = np.unique(hexes[order], return_index=True)
    groups = np.split(order, starts[1:])
    places = summary.load_places()

    feats, zones, spots = [], [], []
    zone_of = np.full(hab["habitat_filter"].shape, -1, "int32")      # 250 m cell -> its zone (spots index)
    for hx, m in zip(uh, groups):
        mg = m[gen[m]]
        has_gen = len(mg) >= min_cells
        sp_cells = {c: m[mask[m]] for c, mask in sp_mask.items()}
        sp_cells = {c: v for c, v in sp_cells.items() if len(v) >= min_cells}
        if not has_gen and not sp_cells:
            continue
        _, ip = pt_tree.query([cx[m].mean(), cy[m].mean()])
        ring = [[lo, la] for la, lo in h3.cell_to_boundary(hx)]
        ring.append(ring[0])
        props = {"h": len(spots), **{f"p{i}": int(clk_pt[ip, i]) for i in range(N_DAYS)}}
        zone_of[rows[m], cols[m]] = len(spots)
        gen_score = _nanmean(score[mg]) if has_gen else None
        if has_gen:
            props.update({f"s{i}": int(round(v)) for i, v in enumerate(gen_score)})
        sp_mean = {c: sp_score[c][v].mean(axis=0) for c, v in sp_cells.items()}
        for c, v in sp_mean.items():
            props.update({f"{c}{i}": int(round(x)) for i, x in enumerate(v)})
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})

        sel = mg if has_gen else m                       # cells behind the "why" bars
        fm = {k: _nanmean(fac[k][sel]) for k in FACTORS}
        im = {k: _nanmean(inp[k][sel]) for k in INPUTS}
        clat, clon = h3.cell_to_latlng(hx)
        counts = np.bincount(tree[m], minlength=6)[1:5]
        alt = (float(np.nanmin(elev[m])), float(np.nanmax(elev[m])))
        spots.append({
            "where": summary.near(clat, clon, places),
            "alt": [int(alt[0]), int(alt[1])],
            "trees": {str(i + 1): round(float(n) / len(m), 2) for i, n in enumerate(counts) if n},
            "f": [[int(round(float(np.nan_to_num(fm[k][d])) * 100)) for k in FACTORS] for d in range(N_DAYS)],
            "in": [[round(float(np.nan_to_num(im[k][d])), 1) for k in INPUTS] for d in range(N_DAYS)],
            "road": rd.describe(float(cx[m].mean()), float(cy[m].mean())) if rd else None,
        })
        zones.append({
            "hex": hx, "lat": clat, "lon": clon, "score": gen_score,
            "species": sp_mean,
            "factors": fm, "inputs": im, "clock": clk_pt[ip],
            "trees": np.bincount(tree[m], minlength=6)[1:] / len(m), "alt": alt,
            "where": spots[-1]["where"],
            "spot": len(spots) - 1,                           # index into spots.json (zone details)
        })
    _write_geojson(PUBLIC / "hexes.geojson", feats)
    (PUBLIC / "spots.json").write_text(json.dumps({"factors": FACTORS, "inputs": INPUTS, "spots": spots},
                                                  separators=(",", ":"), ensure_ascii=False))
    print(f" - {len(feats)} public hexagons ({sum(z['score'] is not None for z in zones)} on the general map)")

    # ---------------------------------------------------------- rain squares (public)
    half = config.load("region")["grids"]["weather_m"] / 2
    p = w["precip"]
    rfeats = []
    for i in range(len(w["x"])):
        x, y = float(w["x"][i]), float(w["y"][i])
        xs, ys = to_ll.transform([x - half, x + half, x + half, x - half, x - half],
                                 [y - half, y - half, y + half, y + half, y - half])
        props = {"r7": float(np.nansum(p[i, t0 - 6: t0 + 1])),
                 "r30": float(np.nansum(p[i, t0 - 29: t0 + 1])),
                 "d": [round(float(v), 1) for v in p[i, t0 - 29: t0 + N_DAYS]]}
        rfeats.append({"type": "Feature", "properties": props,
                       "geometry": {"type": "Polygon", "coordinates": [list(zip(xs, ys))]}})
    _write_geojson(PUBLIC / "rain.geojson", rfeats, ndigits=4)

    # ---------------------------------------------------------- reserves (public info)
    shutil.copy(STATIC / "reserves.geojson", PUBLIC / "reserves.geojson")

    # ---------------------------------------------------------- meta + summary
    sources = config.load("sources")
    mc = S["score"]["mushroom_clock"]
    tot_w = sum(W[k] for k in FACTORS)
    day_info = [{"offset": i, "date": dates[t0 + i], "confidence": confidence(i)} for i in range(N_DAYS)]
    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "weather_run": today.isoformat(), "model": str(w["model"]),
        "days": day_info, "rain_days": dates[t0 - 29: t0 + N_DAYS],
        "public_hexagon_resolution": pv["h3_resolution"],
        "clock": {"opens": mc["window_opens_days_after_pulse"], "closes": mc["window_closes_days_after_pulse"],
                  "soak_mm": S["score"]["rain_pulse"]["soaking_event_mm"]},
        "weights": {k: round(W[k] / tot_w, 4) for k in FACTORS},
        "season_share": round(share, 3),
        "general_map_trees": S["score"]["general_map_trees"],
        "credits": [{"name": v["name"], "credit": v["credit"], "licence": v["licence"],
                     "status": v["licence_status"], "use": v.get("use", "")}
                    for v in sources.values() if isinstance(v, dict) and "credit" in v],
        "safety": "Conditions only. Never eat a wild mushroom based on this map, an app or an AI.",
    }
    (PUBLIC / "meta.json").write_text(json.dumps(meta, indent=1))
    summ = summary.build(zones, day_info, meta, specs)
    (PUBLIC / "summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False))
    print(f" - summary.json: top {len(summ['days'][0]['top_zones'])} zones per day + species")

    export_cells(days, hab, g, to_ll, clk_pt, pt_tree, rd, W, zone_of)
    from . import hotspots
    hotspots.build(summ, g)


def export_cells(days, hab, g, to_ll, clk_pt, pt_tree, rd, W, zone_of):
    """Every 250 m forest square -> PMTiles + details files (public)."""
    OUT = PUBLIC
    S = config.load("scoring")["score"]
    rows, cols = np.nonzero(hab["forest_type"] > 0)
    x = g.west + (cols + 0.5) * g.res
    y = g.north - (rows + 0.5) * g.res
    _, near_pt = pt_tree.query(np.c_[x, y])
    tree = hab["likely_tree"][rows, cols].astype(int)
    band = hab["altitude_band"][rows, cols].astype(int)
    open_ = hab["habitat_filter"][rows, cols] > 0
    gen = open_ & np.isin(tree, S["general_map_trees"])

    # v0.3 soil layer (if built): water-holding (mm, 0-30 cm), pH, tree cover. Missing = no soil props.
    soil = {}
    v03 = config.PROCESSED / "habitat_v03_250m.tif"
    if v03.exists():
        with rasterio.open(v03) as src:
            b = {src.descriptions[i]: src.read(i + 1) for i in range(src.count)}
        awc = b["awc_mm"][rows, cols]
        lo, hi = np.nanpercentile(awc, [33.3, 66.7])                 # "holds water" relative to Cyprus forests
        rel_band = (b["awc_q95_mm"] - b["awc_q05_mm"])[rows, cols] / np.where(awc > 0, awc, np.nan)
        soil = {"awc": awc, "hold": np.where(awc <= lo, 1, np.where(awc <= hi, 2, 3)),
                "ph": b["ph"][rows, cols], "tc": b["tree_cover_pct"][rows, cols],
                "unsure": (rel_band > config.load("soil")["soil_effect"]["neutral_at_rel_band"]) | ~np.isfinite(rel_band)}

    fac = np.stack([np.stack([d[f"f_{k}"][rows, cols] for k in FACTORS], axis=1) for d in days], axis=1)
    inp = np.stack([np.stack([d[k][rows, cols] for k in INPUTS], axis=1) for d in days], axis=1)
    base = np.stack([SP.base_score({k: fac[:, i, j] for j, k in enumerate(FACTORS)}, W)
                     for i in range(N_DAYS)], axis=1)

    # Details file: int16 [cells, 8 days, 6 factors x100 + 5 inputs x10] + [track m, road m]
    info = np.full((len(rows), N_DAYS * (len(FACTORS) + len(INPUTS)) + 2), -1, "int16")
    f100 = np.where(np.isfinite(fac), np.round(fac * 100), -1)
    i10 = np.where(np.isfinite(inp), np.round(inp * 10), -1)
    info[:, : N_DAYS * (len(FACTORS) + len(INPUTS))] = np.concatenate([f100, i10], axis=2).reshape(len(rows), -1)
    if rd:
        dt, dr, _ = rd.distances(x, y)
        info[:, -2] = np.clip(np.nan_to_num(dt, nan=-1), -1, 32000)
        info[:, -1] = np.clip(np.nan_to_num(dr, nan=-1), -1, 32000)
    (OUT / "cells_info.bin").write_bytes(info.astype("<i2").tobytes())
    # "Drive there" pin per square: its centre, float32 [lat, lon]; NaN = in/touching a reserve (no pin).
    # (File name kept from the first version, which stored the nearest road point.)
    clo, cla = to_ll.transform(x, y)
    pins = roads.square_pins(cla, clo, hab["reserve_id"][rows, cols])
    (OUT / "cells_road.bin").write_bytes(pins.astype("<f4").tobytes())
    (OUT / "cells_info.json").write_text(json.dumps({
        "cells": len(rows), "days": N_DAYS, "factors": FACTORS, "inputs": INPUTS,
        "layout": "int16 little-endian; per cell: days x (factors x100, inputs x10), then track_m, road_m; -1 = none",
        "road_layout": "cells_road.bin: float32 little-endian; per cell: lat, lon of the square's centre (Drive there pin); NaN = in/touching a nature reserve"}))

    feats = []
    for n, (r, c) in enumerate(zip(rows, cols)):
        x0 = g.west + c * g.res; y1 = g.north - r * g.res
        xs, ys = to_ll.transform([x0, x0 + g.res, x0 + g.res, x0, x0], [y1, y1, y1 - g.res, y1 - g.res, y1])
        props = {f"s{i}": (int(round(d["score"][r, c])) if np.isfinite(d["score"][r, c]) else None)
                 for i, d in enumerate(days)}
        props.update({f"b{i}": int(round(base[n, i])) for i in range(N_DAYS)})
        props.update({f"p{i}": int(clk_pt[near_pt[n], i]) for i in range(N_DAYS)})
        props.update({"i": n, "tree": int(tree[n]), "band": int(band[n]), "g": int(gen[n]),
                      "elev": int(round(float(np.nan_to_num(hab["elevation_m"][r, c])))),
                      "closed": int(not open_[n])})
        if zone_of[r, c] >= 0:
            props["h"] = int(zone_of[r, c])                       # its ~2 km zone in spots.json
        if soil and np.isfinite(soil["awc"][n]):
            props.update({"awc": int(round(float(soil["awc"][n]))), "hold": int(soil["hold"][n]),
                          "ph": int(round(float(soil["ph"][n]) * 10)), "su": int(bool(soil["unsure"][n]))})
        if soil and np.isfinite(soil["tc"][n]):
            props["tc"] = int(round(float(soil["tc"][n])))
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": [list(zip(xs, ys))]}})
    gj = OUT / "cells.geojson"
    _write_geojson(gj, feats)
    write_pmtiles(gj, OUT / "cells.pmtiles", "cells", 6, 13)
    gj.unlink()
    print(f" - {len(feats)} public 250 m forest squares + details")


if __name__ == "__main__":
    build(latest_run())
