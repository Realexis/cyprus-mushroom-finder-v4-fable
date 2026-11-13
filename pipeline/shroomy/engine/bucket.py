"""Soil-water bucket (v0.3 spec 3.2 step 2). Pure numpy, all settings from config/engine.yaml.

One bucket per 250 m square. Each day:
    rain in    = rain - canopy interception
    evaporation = Hargreaves ET0 x crop factor x slope factor x dryness factor
    drainage   = share of the water above `drain_above_fill` that leaves
    W = clip(W + rain in - evaporation - drainage, 0, capacity)
"""
import numpy as np

GSC = 0.0820            # solar constant, MJ m-2 min-1 [FAO56]
DRAIN_NAMES = {0: "unknown", 1: "fast", 2: "medium", 3: "slow"}   # soil.yaml drainage classes


def extraterrestrial_radiation(lat_deg, doy):
    """Ra in MJ m-2 day-1 for latitude (degrees) and day of year (FAO-56 eq. 21)."""
    phi = np.radians(np.asarray(lat_deg, "float64"))
    j = np.asarray(doy, "float64")
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365)
    delta = 0.409 * np.sin(2 * np.pi * j / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    return (24 * 60 / np.pi) * GSC * dr * (ws * np.sin(phi) * np.sin(delta)
                                           + np.cos(phi) * np.cos(delta) * np.sin(ws))


def hargreaves_et0(tmean, tmin, tmax, ra):
    """Reference evaporation, mm/day (Hargreaves-Samani, FAO-56 eq. 52). ra in MJ m-2 day-1."""
    rng = np.sqrt(np.clip(np.asarray(tmax, "float64") - tmin, 0, None))
    return np.clip(0.0023 * (np.asarray(tmean, "float64") + 17.8) * rng * ra * 0.408, 0, None)


def slope_factor(shade, cfg):
    """Sunny slopes dry faster: shade 0 -> sunny_k, shade 1 -> shade_k."""
    s = np.clip(np.nan_to_num(np.asarray(shade, "float64"), nan=0.5), 0, 1)
    return cfg["sunny_k"] + (cfg["shade_k"] - cfg["sunny_k"]) * s


def certainty(mean, q05, q95, neutral_at_rel_band):
    """0..1: how much to trust a SoilGrids value. Wide band (relative to the mean) -> 0."""
    mean = np.asarray(mean, "float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = (np.asarray(q95, "float64") - q05) / mean
    c = np.clip(1 - rel / neutral_at_rel_band, 0, 1)
    return np.where(np.isfinite(c) & (mean > 0), c, 0.0)


def blended_capacity(awc, q05, q95, island_median, neutral_at_rel_band, cfg):
    """Bucket size in mm, "blend by certainty": move from the island median towards
    SoilGrids only as far as SoilGrids is sure. No data -> the median."""
    med = island_median if np.isfinite(island_median) else cfg["capacity_fallback_mm"]
    awc = np.asarray(awc, "float64")
    c = certainty(awc, q05, q95, neutral_at_rel_band)
    cap = med + (np.nan_to_num(awc, nan=med) - med) * c
    return np.maximum(cap, cfg["capacity_min_mm"])


def drain_rate(drainage_class, cfg):
    """Daily drainage share per square from the soil.yaml drainage class (0..3)."""
    d = np.nan_to_num(np.asarray(drainage_class, "float64"), nan=0).astype(int)
    table = np.array([cfg["drain_per_day"][DRAIN_NAMES[k]] for k in range(4)])
    return table[np.clip(d, 0, 3)]


def bucket_step(w, rain, et0, cap, k_evap, k_drain, cfg):
    """One day. All arrays per square. Returns the new water (mm)."""
    rain_in = np.clip(rain - cfg["interception_mm"], 0, None)
    w = np.minimum(w + rain_in, cap)
    # dryness: full evaporation above p x cap, then slows in step with the fill
    fill = w / cap
    dry = np.clip(fill / cfg["readily_available_fraction"], 0, 1)
    w = w - et0 * cfg["crop_factor"] * k_evap * dry
    w = w - k_drain * np.clip(w - cfg["drain_above_fill"] * cap, 0, None)
    return np.clip(w, 0, cap)


def run_bucket(rain, et0, cap, k_evap, k_drain, cfg, w0=None):
    """Whole run. rain, et0: (squares, days). Returns fill 0..1, shape (squares, days)."""
    cap = np.asarray(cap, "float64")
    w = cap * cfg["start_fill"] if w0 is None else np.asarray(w0, "float64")
    fill = np.empty(rain.shape, "float32")
    for t in range(rain.shape[1]):
        w = bucket_step(w, rain[:, t], et0[:, t], cap, k_evap, k_drain, cfg)
        fill[:, t] = w / cap
    return fill
