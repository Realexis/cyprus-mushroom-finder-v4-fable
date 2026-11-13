"""Run one species profile on every square, for every day of a weather run (v0.3 spec 3.2).

Vectorised over squares, looping over days. Inputs come from inputs.py (or tests).
"""
import numpy as np

from .. import config
from . import bucket as B
from .cycle import run_cycle
from .profile import engine_params
from .score import combine, habitat_fit, season_prior, temperature_fit, water_fit
from .soiltemp import soil_temp_proxy


def rolling_sum(x, days):
    """Sum over the `days` days ending on each day (inclusive). x: (squares, days)."""
    c = np.cumsum(np.nan_to_num(x, nan=0.0), axis=1, dtype="float64")
    out = c.copy()
    out[:, days:] = c[:, days:] - c[:, :-days]
    return out


def prepare_water(inp, ecfg, scfg):
    """Species-independent part: bucket fill, soil temperature, frost. Run once, share across species."""
    bc = ecfg["bucket"]
    sq = inp["squares"]
    ra = B.extraterrestrial_radiation(inp["lat"][:, None], inp["doy"][None, :])
    et0 = B.hargreaves_et0(inp["tmean"], inp["tmin"], inp["tmax"], ra)
    cap = B.blended_capacity(sq["awc_mm"], sq["awc_q05_mm"], sq["awc_q95_mm"], inp["island_awc_median"],
                             scfg["soil_effect"]["neutral_at_rel_band"], bc)
    fill = B.run_bucket(inp["precip"], et0, cap, B.slope_factor(sq["shade_score"], bc),
                        B.drain_rate(sq["drainage"], bc), bc)
    st = ecfg["soil_temperature"]
    tsoil = inp.get("tsoil")
    if tsoil is None:
        tsoil = soil_temp_proxy(inp["tmean"], st["proxy_days"])
    return {"et0": et0.astype("float32"), "capacity_mm": cap, "fill": fill, "tsoil": tsoil,
            "frost": inp["tmin"] <= st["frost_air_min_c"]}


def run_species(prof, inp, water, ecfg=None, scfg=None):
    """One profile -> per-square, per-day score (0..1) and every part of it."""
    ecfg = ecfg or config.load("engine")
    scfg = scfg or config.load("soil")
    p = engine_params(prof, ecfg)
    sq = inp["squares"]

    hab = habitat_fit(sq, prof, ecfg["habitat"], scfg["habitat_v03"]["tree_cover_min_pct"],
                      scfg["soil_effect"]["neutral_at_rel_band"])
    wfit = water_fit(water["fill"], *p["water"])
    tfit = temperature_fit(water["tsoil"], p["temp"])
    rain_win = rolling_sum(inp["precip"], p["trigger_days"])
    cyc = run_cycle(rain_win, water["fill"], water["tsoil"], tfit > 0, water["frost"], p, ecfg["cycle"])
    prior = season_prior(inp["month"], p["season"], ecfg["season_prior"]["floor"])[None, :]
    score = combine(hab[:, None], wfit, tfit, cyc["factor"], prior)
    return {"score": score.astype("float32"), "habitat": hab.astype("float32"),
            "water": wfit.astype("float32"), "temperature": tfit.astype("float32"),
            "cycle": cyc["factor"], "state": cyc["state"], "dd": cyc["dd"], "days": cyc["days"],
            "trigger_t": cyc["trigger_t"], "prior": np.broadcast_to(prior, score.shape),
            "unused_cues": p["unused_cues"]}


def general_map(results):
    """General map = the best score among the species shown (spec 3.2 step 6).

    Returns (best score, index of the species that gave it)."""
    stack = np.stack([r["score"] for r in results])
    return stack.max(axis=0), stack.argmax(axis=0).astype("int8")
