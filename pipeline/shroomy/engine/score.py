"""Fits and the multiplied species score (v0.3 spec 3.2 steps 1 and 5). Pure numpy.

    species score = habitat fit x water fit x temperature fit x cycle factor x season prior

MULTIPLY, never a weighted sum: if any part is near zero, the score is near zero.
Every part is 0..1, so the score is 0..1 too (the site shows words, not numbers).
"""
import numpy as np

from ..score.factors import ramp, trapezoid
from .bucket import certainty


# ------------------------------------------------------------------ the four day-by-day fits
def water_fit(fill, zero_at, full_at):
    return ramp(fill, zero_at, full_at)


def temperature_fit(tsoil, window):
    """window = (min, best_low, best_high, max) in C. Trapezoid; a point best works too."""
    lo, b0, b1, hi = window
    x = np.asarray(tsoil, "float64")
    up = np.clip((x - lo) / max(b0 - lo, 1e-6), 0, 1)
    down = np.clip((hi - x) / max(hi - b1, 1e-6), 0, 1)
    return np.minimum(up, down)


def season_prior(month, season, floor):
    """Soft prior 0.5..1 (spec). season = 12 values 0..1 (jan..dec); 0 -> floor, 1 -> 1."""
    v = np.asarray(season, "float64")[np.asarray(month) - 1]
    return floor + (1 - floor) * np.clip(v, 0, 1)


def combine(habitat, water, temp, cycle, prior):
    """The species score, 0..1. Broadcasts (squares,) against (squares, days)."""
    return habitat * water * temp * cycle * prior


# ------------------------------------------------------------------ habitat (fixed per square)
def _ph_mismatch(ph, want, h):
    a, k, r = h["ph_acid_below"], h["ph_alkaline_above"], h["ph_ramp"]
    if want == "acid":
        return ramp(ph, a, a + r)
    if want == "alkaline":
        return 1 - ramp(ph, k - r, k)
    if want == "neutral":
        return np.maximum(ramp(ph, k, k + r), 1 - ramp(ph, a - r, a))
    return np.zeros(np.shape(ph))                       # any / unknown


def soil_fit(sq, pref, h, neutral_at_rel_band):
    """Soft soil multiplier, between soil_pref.weight and 1.0 (spec 3.9).

    Each preference gives a mismatch 0..1, scaled by how sure the data is.
    The biggest one sets the factor, so the factor never drops below the weight.
    """
    n = len(sq["ph"])
    low = float(pref.get("weight", 1.0))
    ph_want = pref.get("ph", "unknown")
    tex = pref.get("texture", "unknown")
    rock = pref.get("rock", "unknown")
    worst = np.zeros(n)

    if ph_want not in ("any", "unknown"):
        ph = np.nan_to_num(sq["ph"], nan=7.0)
        sure = certainty(sq["ph"], sq["ph_q05"], sq["ph_q95"], neutral_at_rel_band)
        worst = np.maximum(worst, _ph_mismatch(ph, ph_want, h) * sure)

    if tex in ("sandy", "clay"):
        d = np.nan_to_num(sq["drainage"], nan=0).astype(int)          # 1 fast, 2 medium, 3 slow
        table = {"sandy": [0, 0, 0.5, 1], "clay": [0, 1, 0.5, 0]}[tex]
        worst = np.maximum(worst, np.array(table)[np.clip(d, 0, 3)] * sq["awc_certainty"])

    if rock in ("calcareous", "igneous"):
        other = sq["igneous_fraction"] if rock == "calcareous" else sq["calcareous_frac"]
        worst = np.maximum(worst, np.clip(np.nan_to_num(other), 0, 1))  # geology map: taken as sure

    return 1 - (1 - low) * worst


def habitat_fit(sq, prof, h, tree_cover_min, neutral_at_rel_band):
    """0..1 per square: host trees or land cover, tree cover, altitude, soil, burns. Reserves = 0.

    sq: dict of per-square arrays (see inputs.py). h: engine.yaml `habitat`.
    """
    n = len(sq["likely_tree"])
    tree = np.nan_to_num(sq["likely_tree"], nan=0).astype(int)

    # Host trees (likely tree per square) need enough tree cover (soft ramp).
    tw = np.zeros(n)
    for name, w in (prof["host_trees"] or {}).items():
        code = h["tree_codes"].get(name)
        if code is not None:                                 # e.g. kermes_oak: no map layer yet
            tw = np.where(tree == code, np.maximum(tw, w), tw)
    tmin = prof.get("min_tree_cover_pct", tree_cover_min)
    cover = ramp(np.nan_to_num(sq["tree_cover_pct"], nan=0), tmin - h["tree_cover_soft_pct"], tmin)
    base = tw * cover

    # Land-cover partners (fields, scrub ...): weight x share of the square.
    for name, w in (prof.get("land_cover") or {}).items():
        if name not in h["land_cover"]:
            raise ValueError(f"unknown land_cover {name!r}; allowed: {h['land_cover']}")
        base = np.maximum(base, w * np.clip(np.nan_to_num(sq[name]), 0, 1))

    lo, hi = prof["altitude_range"]
    m = h["altitude_soft_m"]
    alt = trapezoid(np.nan_to_num(sq["elevation_m"], nan=0), lo - m, lo, hi, hi + m)

    fit = base * alt * soil_fit(sq, prof["soil_pref"], h, neutral_at_rel_band)

    if (prof["extra_cues"] or {}).get("needs_burn"):
        fit = fit * ramp(np.nan_to_num(sq["clc_burnt"]), 0, h["burn_full_at_frac"])

    closed = (np.nan_to_num(sq["reserve_id"]) > 0) | (tree == 5)     # nature reserves stay CLOSED
    return np.where(closed, 0.0, fit)
