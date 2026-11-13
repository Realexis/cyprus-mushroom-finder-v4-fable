"""Check the water bucket against the weather model's own soil moisture (audit step 11).

Every weather run holds `soil`: ECMWF soil moisture, top 7 cm (m3/m3). The engine does not use it:
the bucket is what lets shade and soil differ from square to square. But if the bucket is right,
it should rise and fall with the model's soil moisture. This reports how well they move together.

- r_level:  correlation of bucket fill and model soil moisture, day by day, per square (median).
- r_change: the same for the day-to-day changes (wetting and drying events).
- lag:      the shift in days (-3..+3) that fits best (bucket later than the model = positive).

Only observed days are used (not the forecast).

Run:  uv run python -m shroomy.engine.check_bucket <run_file.npz> [<run_file.npz> ...]
"""
import json
import sys
from pathlib import Path

import numpy as np

from .. import config
from ..grid import habitat_grid
from ..score.downscale import Interpolator
from . import inputs as I
from .runner import prepare_water

SAMPLE_EVERY = 8


def _corr_rows(a, b):
    """Pearson r per row of two (n, d) arrays; NaN where a row is flat."""
    a = a - a.mean(axis=1, keepdims=True)
    b = b - b.mean(axis=1, keepdims=True)
    den = np.sqrt((a * a).sum(axis=1) * (b * b).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return (a * b).sum(axis=1) / den


def compare(run_file):
    E, S = config.load("engine"), config.load("soil")
    w = np.load(run_file)
    if "soil" not in w.files or not np.isfinite(w["soil"]).any():
        return {"run": Path(run_file).name, "error": "no soil moisture in this file"}
    with __import__("rasterio").open(config.PROCESSED / "habitat_250m.tif") as src:
        d = list(src.descriptions)
        tree = src.read(d.index("likely_tree") + 1)
        land = src.read(d.index("land_fraction") + 1)
    inp = I.build(run_file, (land > 0.5) & (tree > 0) & (tree < 5))          # forest squares
    keep = np.arange(len(inp["rows"]))[::SAMPLE_EVERY]
    inp = I.subset(inp, keep)
    fill = prepare_water(inp, E, S)["fill"]
    g = habitat_grid()
    cx = g.west + (inp["cols"] + 0.5) * g.res
    cy = g.north - (inp["rows"] + 0.5) * g.res
    sm = Interpolator(np.c_[w["x"], w["y"]], np.c_[cx, cy])(np.nan_to_num(w["soil"], nan=np.nanmean(w["soil"])))
    dates = [str(x) for x in w["dates"]]
    t0 = dates.index(str(w["today"]))
    obs = slice(0, t0 + 1)                                   # observed days only
    f, s = fill[:, obs].astype("float64"), sm[:, obs].astype("float64")
    skip = 7                                                 # the bucket's first week is spin-up
    f, s = f[:, skip:], s[:, skip:]
    r_level = _corr_rows(f, s)
    r_change = _corr_rows(np.diff(f, axis=1), np.diff(s, axis=1))
    lags = {}
    for k in range(-3, 4):
        if k >= 0:
            a, b = f[:, k:], s[:, : s.shape[1] - k]
        else:
            a, b = f[:, :k], s[:, -k:]
        lags[k] = float(np.nanmedian(_corr_rows(a, b)))
    best = max(lags, key=lags.get)
    island_f = np.median(f, axis=0)
    island_s = np.median(s, axis=0)
    return {"run": Path(run_file).name, "days": int(f.shape[1]), "first": dates[skip], "last": dates[t0],
            "squares": int(f.shape[0]),
            "r_level_median": round(float(np.nanmedian(r_level)), 2),
            "r_level_p10_p90": [round(float(np.nanpercentile(r_level, p)), 2) for p in (10, 90)],
            "r_change_median": round(float(np.nanmedian(r_change)), 2),
            "best_lag_days": int(best), "r_at_lag": {k: round(v, 2) for k, v in lags.items()},
            "island_r_level": round(float(np.corrcoef(island_f, island_s)[0, 1]), 2),
            "island_fill_median": [round(float(x), 2) for x in island_f],
            "island_soil_median": [round(float(x), 3) for x in island_s]}


if __name__ == "__main__":
    for f in sys.argv[1:]:
        r = compare(f)
        print(json.dumps({k: v for k, v in r.items() if not k.startswith("island_") or k == "island_r_level"}, indent=1))
