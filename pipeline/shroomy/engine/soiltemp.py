"""Soil temperature and degree-days (v0.3 spec 3.2 steps 3-4). Pure numpy.

Temperatures arrive already corrected to each square's height (lapse rate, see inputs.py).
"""
import numpy as np


def soil_temp_proxy(tair_mean, proxy_days, t0=None):
    """Soil follows the air slowly: running mean with a lag of about `proxy_days`.

    Used until Open-Meteo soil temperature is fetched (TODO-facts P2).
    tair_mean: (squares, days). Returns the same shape.
    """
    a = 1.0 / max(float(proxy_days), 1.0)
    tair = np.asarray(tair_mean, "float64")
    out = np.empty(tair.shape, "float32")
    ts = tair[:, 0] if t0 is None else np.asarray(t0, "float64")
    for t in range(tair.shape[1]):
        ts = ts + a * (tair[:, t] - ts)
        out[:, t] = ts
    return out


def degree_days(tsoil, base_c):
    """Degree-days of one day: how far the soil is above the base temperature (never negative)."""
    return np.clip(np.asarray(tsoil, "float64") - base_c, 0, None)
