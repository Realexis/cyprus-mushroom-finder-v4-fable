"""Build engine inputs from a weather run (data/processed/weather/run_*.npz) and the
fixed 250 m layers (habitat_250m.tif, habitat_v03_250m.tif).

Kept apart from the engine so a live daily job can plug in other weather later (spec 3.1).
"""
from datetime import date

import numpy as np
import rasterio

from .. import config
from ..grid import habitat_grid
from ..score import factors as F
from ..score.downscale import Interpolator

V1_BANDS = ["likely_tree", "elevation_m", "reserve_id", "shade_score", "igneous_fraction", "land_fraction"]


def _bands(path, names=None):
    with rasterio.open(path) as src:
        d = list(src.descriptions)
        names = names or d
        return {n: src.read(d.index(n) + 1) for n in names}


def build(run_file, squares="land"):
    """squares: "land" (all land) or a boolean (rows, cols) mask."""
    S = config.load("scoring")["score"]
    lapse = S["temperature"]["lapse_rate_c_per_km"]
    g = habitat_grid()
    v1 = _bands(config.PROCESSED / "habitat_250m.tif", V1_BANDS)
    v3 = _bands(config.PROCESSED / "habitat_v03_250m.tif")
    mask = (v1["land_fraction"] > 0.5) if isinstance(squares, str) else squares
    rows, cols = np.nonzero(mask)

    sq = {k: v[rows, cols].astype("float32") for k, v in {**v1, **v3}.items()}
    with np.errstate(invalid="ignore"):
        forest = (v1["likely_tree"] > 0) & np.isfinite(v3["awc_mm"])
    island_awc_median = float(np.nanmedian(v3["awc_mm"][forest])) if forest.any() else float("nan")
    sq["awc_certainty"] = _awc_certainty(sq)

    w = np.load(run_file)
    cx = g.west + (cols + 0.5) * g.res
    cy = g.north - (rows + 0.5) * g.res
    interp = Interpolator(np.c_[w["x"], w["y"]], np.c_[cx, cy])
    elev = np.nan_to_num(sq["elevation_m"], nan=0.0)

    def temp(name):          # to sea level at the points, spread, then up to each square's height
        t0 = F.to_sea_level(w[name], w["elev_om"][:, None], lapse)
        return F.from_sea_level(interp(t0), elev[:, None], lapse).astype("float32")

    days = [date.fromisoformat(str(d)) for d in w["dates"]]
    return {
        "dates": [d.isoformat() for d in days],
        "today_index": [str(d) for d in w["dates"]].index(str(w["today"])),
        "doy": np.array([d.timetuple().tm_yday for d in days]),
        "month": np.array([d.month for d in days]),
        "rows": rows, "cols": cols,
        "lat": interp(w["lat"]),
        "precip": np.clip(interp(np.nan_to_num(w["precip"])), 0, None).astype("float32"),
        "tmean": temp("tmean"), "tmin": temp("tmin"), "tmax": temp("tmax"),
        # Open-Meteo soil temperature 0-7 cm (audit step 7), moved to each square's height with the air
        # lapse rate [GUESS for soil]. Days without it are filled from the air estimate (runner.py).
        "tsoil": temp("tsoil_om") if _has(w, "tsoil_om") else None,
        "squares": sq,
        "island_awc_median": island_awc_median,
    }


def _has(w, name):
    return name in w.files and np.isfinite(w[name]).any()


def subset(inp, keep):
    """Keep only some squares (boolean or index array over the squares)."""
    out = dict(inp)
    for k in ("rows", "cols", "lat", "precip", "tmean", "tmin", "tmax"):
        out[k] = inp[k][keep]
    if inp.get("tsoil") is not None:
        out["tsoil"] = inp["tsoil"][keep]
    out["squares"] = {k: v[keep] for k, v in inp["squares"].items()}
    return out


def _awc_certainty(sq):
    from .bucket import certainty
    neutral = config.load("soil")["soil_effect"]["neutral_at_rel_band"]
    return certainty(sq["awc_mm"], sq["awc_q05_mm"], sq["awc_q95_mm"], neutral)
