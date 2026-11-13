"""Burnt areas with fire dates (EFFIS), one 250 m band per fire year (audit step 8).

Source: EFFIS (European Forest Fire Information System, Copernicus Emergency Management Service),
WFS layer `modis.ba.poly` (burnt areas mapped from MODIS / Sentinel-2, fires of about 30 ha and up).
Licence: see config/sources.yaml `effis`.

Output: data/processed/effis_burn_250m.tif, bands `burn_<year>` = share (0..1) of each 250 m square
burnt in that year. The engine (engine/inputs.py) turns them into:
- burn_recent: burnt in the 2 calendar years before the run's year (morels fruit in the first
  springs after a fire [LAR16]);
- burn_5y:     burnt in the run's year or the 5 before (no longer habitat for tree partners [GUESS]).

Run:  uv run python -m shroomy.habitat.effis [--refresh]
"""
import json
import sys

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.features import rasterize

from .. import config
from ..grid import block_mean, habitat_grid

URL = "https://maps.effis.emergency.copernicus.eu/effis"
PARAMS = {"service": "WFS", "version": "1.1.0", "request": "GetFeature", "typename": "ms:modis.ba.poly",
          "bbox": "34.4,32.1,35.8,34.7,urn:ogc:def:crs:EPSG::4326", "outputFormat": "geojson"}
HEADERS = {"User-Agent": "cyprus-mushroom-finder/0.1 (non-commercial, static site)"}
RAW = config.RAW / "effis" / "modis_ba_poly_cyprus.geojson"
OUT = config.PROCESSED / "effis_burn_250m.tif"
RECENT_YEARS = 2          # [LAR16] burn morels in the first springs after a fire
TREE_PARTNER_YEARS = 5    # [GUESS] audit step 8


def fetch(refresh=False):
    if RAW.exists() and not refresh:
        return RAW
    r = requests.get(URL, params=PARAMS, headers=HEADERS, timeout=120)
    r.raise_for_status()
    d = r.json()
    d["features"] = [f for f in d["features"] if f["properties"].get("COUNTRY") == "CY"]
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(d))
    return RAW


def build(refresh=False):
    g = habitat_grid()
    g25 = g.at(25)
    ba = gpd.read_file(fetch(refresh)).to_crs(g.crs)
    ba["year"] = ba["FIREDATE"].astype(str).str[:4].astype(int)
    years = sorted(ba["year"].unique())
    with rasterio.open(OUT, "w", driver="GTiff", width=g.width, height=g.height, count=len(years), dtype="float32",
                       crs=g.crs, transform=g.transform, nodata=np.nan, compress="deflate", predictor=3,
                       tiled=True) as dst:
        for i, y in enumerate(years, start=1):
            sel = ba[ba["year"] == y]
            r25 = rasterize(((geom, 1) for geom in sel.geometry), out_shape=(g25.height, g25.width),
                            transform=g25.transform, dtype="uint8")
            dst.write(block_mean(r25.astype("float32"), 10).astype("float32"), i)
            dst.set_band_description(i, f"burn_{y}")
    summ = {int(y): {"fires": int((ba["year"] == y).sum()), "ha": round(float(ba.loc[ba["year"] == y, "AREA_HA"]
                                                                             .astype(float).sum()))} for y in years}
    print(f"-> {OUT.name}: {len(years)} fire years", summ)
    return OUT


def burn_layers(year, path=OUT):
    """(burn_recent, burn_5y) 2-D arrays for a run in calendar `year`, or None if the file is missing."""
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        bands = {int(d.split("_")[1]): src.read(i + 1) for i, d in enumerate(src.descriptions)}
    zero = np.zeros_like(next(iter(bands.values())))

    def share(years):
        sel = [np.nan_to_num(bands[y]) for y in years if y in bands]
        return np.clip(np.maximum.reduce(sel), 0, 1) if sel else zero

    recent = share(range(year - RECENT_YEARS, year))
    five = share(range(year - TREE_PARTNER_YEARS, year + 1))
    return recent.astype("float32"), five.astype("float32")




def latest_fire(year, path=OUT, years_back=TREE_PARTNER_YEARS, min_share=0.05):
    """(fire_year, burnt_share) 2-D arrays for a run in calendar `year`: the most recent fire year in the
    run's year or the `years_back` before that burned at least `min_share` of the square (0 = none),
    and the burnt share used for tree partners (burn_5y). None if the file is missing."""
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        bands = {int(d.split("_")[1]): np.nan_to_num(src.read(i + 1)) for i, d in enumerate(src.descriptions)}
    shape = next(iter(bands.values())).shape
    fy = np.zeros(shape, "int16")
    for y in range(year - years_back, year + 1):          # oldest first, so the newest wins
        if y in bands:
            fy = np.where(bands[y] >= min_share, y, fy).astype("int16")
    return fy, burn_layers(year, path)[1]


if __name__ == "__main__":
    build(refresh="--refresh" in sys.argv)
