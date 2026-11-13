"""Giant fennel near each 250 m square, from GBIF records (audit step 10).

The fennel king oyster lives on the roots of giant fennel (Ferula communis). There is no fennel map,
so the engine used fields and grassland at half weight. GBIF holds a few hundred dated, placed
giant fennel records in Cyprus. A square whose centre is within NEAR_M of a record gets
`fennel_near` = 1 (full weight in species/pfe.yaml); the rest keep the half-weight stand-in.

Honest limit: records show where people looked, not everywhere fennel grows.

Licences: only records under CC0, CC BY or CC BY-NC are used (fine for this non-commercial site).
Every dataset used is listed with its licence in data/processed/fennel_datasets.json and credited
in config/sources.yaml (`gbif_fennel`).

Output: data/processed/fennel_250m.tif (band `fennel_near`, 0 or 1).
Run:  uv run python -m shroomy.habitat.fennel [--refresh]
"""
import json
import sys

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from scipy.spatial import cKDTree

from .. import config
from ..grid import habitat_grid

GBIF = "https://api.gbif.org/v1"
TAXON = 8048981                    # Ferula communis L. (GBIF backbone)
HEADERS = {"User-Agent": "cyprus-mushroom-finder/0.1 (non-commercial, static site)"}
RAW = config.RAW / "gbif" / "ferula_communis_cy.json"
OUT = config.PROCESSED / "fennel_250m.tif"
DATASETS = config.PROCESSED / "fennel_datasets.json"
NEAR_M = 500                       # [GUESS] audit step 10
MAX_UNCERTAINTY_M = 1000           # [GUESS] a record placed less precisely than this cannot place a 500 m circle
OK_LICENCES = {"CC0_1_0": "CC0", "CC_BY_4_0": "CC BY 4.0", "CC_BY_NC_4_0": "CC BY-NC 4.0",
               "http://creativecommons.org/publicdomain/zero/1.0/legalcode": "CC0",
               "http://creativecommons.org/licenses/by/4.0/legalcode": "CC BY 4.0",
               "http://creativecommons.org/licenses/by-nc/4.0/legalcode": "CC BY-NC 4.0"}


def fetch(refresh=False):
    if RAW.exists() and not refresh:
        return json.loads(RAW.read_text())
    out, offset = [], 0
    while True:
        r = requests.get(f"{GBIF}/occurrence/search", headers=HEADERS, timeout=60,
                         params={"country": "CY", "taxonKey": TAXON, "hasCoordinate": "true",
                                 "hasGeospatialIssue": "false", "limit": 300, "offset": offset})
        r.raise_for_status()
        d = r.json()
        out += [{k: x.get(k) for k in ("key", "decimalLatitude", "decimalLongitude", "coordinateUncertaintyInMeters",
                                        "license", "datasetKey", "eventDate", "basisOfRecord")} for x in d["results"]]
        offset += 300
        if d.get("endOfRecords", True):
            break
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(out))
    return out


def usable(recs):
    """Records with an allowed licence and a precise enough position."""
    keep = []
    for x in recs:
        if x.get("license") not in OK_LICENCES:
            continue
        if x.get("basisOfRecord") == "LIVING_SPECIMEN":         # a garden plant, not wild fennel
            continue
        u = x.get("coordinateUncertaintyInMeters")
        if u is not None and u > MAX_UNCERTAINTY_M:
            continue
        keep.append(x)
    return keep


def near_mask(px, py, g, near_m=NEAR_M):
    """(height, width) 0/1: square centres within near_m of any point (grid CRS metres)."""
    xs = g.west + (np.arange(g.width) + 0.5) * g.res
    ys = g.north - (np.arange(g.height) + 0.5) * g.res
    X, Y = np.meshgrid(xs, ys)
    if not len(px):
        return np.zeros(X.shape, "float32")
    d, _ = cKDTree(np.c_[px, py]).query(np.c_[X.ravel(), Y.ravel()], distance_upper_bound=near_m)
    return np.isfinite(d).reshape(X.shape).astype("float32")


def build(refresh=False):
    g = habitat_grid()
    recs = usable(fetch(refresh))
    to_g = Transformer.from_crs("EPSG:4326", g.crs, always_xy=True)
    px, py = to_g.transform([x["decimalLongitude"] for x in recs], [x["decimalLatitude"] for x in recs])
    near = near_mask(np.asarray(px), np.asarray(py), g)
    with rasterio.open(OUT, "w", driver="GTiff", width=g.width, height=g.height, count=1, dtype="float32",
                       crs=g.crs, transform=g.transform, nodata=np.nan, compress="deflate", tiled=True) as dst:
        dst.write(near, 1)
        dst.set_band_description(1, "fennel_near")
    # Credit every dataset used, with its licence.
    keys = sorted({x["datasetKey"] for x in recs})
    ds = []
    for k in keys:
        r = requests.get(f"{GBIF}/dataset/{k}", headers=HEADERS, timeout=60)
        title = r.json().get("title", k) if r.ok else k
        lic = sorted({OK_LICENCES[x["license"]] for x in recs if x["datasetKey"] == k})
        ds.append({"key": k, "title": title, "licence": ", ".join(lic),
                   "records": sum(x["datasetKey"] == k for x in recs), "url": f"https://www.gbif.org/dataset/{k}"})
    DATASETS.write_text(json.dumps(ds, indent=1, ensure_ascii=False))
    print(f"-> {OUT.name}: {len(recs)} usable records, {int(near.sum())} squares near fennel, {len(ds)} datasets")
    for d in ds:
        print(f"   {d['records']:>4}  {d['licence']:<14} {d['title']}")
    return OUT


if __name__ == "__main__":
    build(refresh="--refresh" in sys.argv)
