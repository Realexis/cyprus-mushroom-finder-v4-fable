"""v0.3 habitat + soil layer (fixed, built once). Everything is cached in data/raw/v03/.

New 250 m layers (on the same grid as habitat_250m.tif):
- tree cover density (Copernicus HRL TCD 2018, 10 m)  -> fixes "forest" that is really scrub
- grassland (Copernicus HRL Grassland 2018, 10 m) and CORINE 2018 classes:
  arable, pasture, natural grassland, sclerophyllous scrub, transitional woodland-shrub, burnt
- soil from SoilGrids 2.0 (WCS, 250 m, CC BY 4.0): available water capacity 0-30 cm (+ Q05/Q95),
  sand, clay, pH (+ Q05/Q95), organic carbon, drainage class
- calcareous share of each square (geology map, formation grouping in config/soil.yaml [DRAFT])

Burn scars with fire year (EFFIS) are NOT here yet: the EFFIS services did not answer
(2026-11-13). CORINE "burnt areas" (around 2018, no year) is used meanwhile.

Output: data/processed/habitat_v03_250m.tif (named bands) + habitat_v03_summary.json
Run:    uv run python -m shroomy.habitat.v03
"""
import json
import subprocess

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT

from .. import config
from ..grid import block_mean, habitat_grid
from .fetch import _arcgis_geojson, _get

RAW = config.RAW / "v03"
EEA = "https://image.discomap.eea.europa.eu/arcgis/rest/services"
CLC = f"{EEA}/Corine/CLC2018_WM/MapServer/0"
CLC_CLASSES = {          # CORINE 2018 level-3 codes
    "clc_arable": ["211", "212", "213"],
    "clc_pasture": ["231"],
    "clc_grassland": ["321"],
    "clc_sclerophyll": ["323"],         # maquis/garrigue incl. rock-rose scrub [SPEC]
    "clc_transitional": ["324"],        # transitional woodland-shrub
    "clc_burnt": ["334"],
}


# ------------------------------------------------------------------ 10 m EEA rasters
def fetch_eea_10m(service: str, name: str):
    """A 10 m HRL layer for our grid, in chunks, via the EEA image service (like forest type)."""
    g = habitat_grid().at(10)
    out_dir = RAW / name
    out_dir.mkdir(parents=True, exist_ok=True)
    chunk, parts = 4000, []
    for r0 in range(0, g.height, chunk):
        for c0 in range(0, g.width, chunk):
            h, w = min(chunk, g.height - r0), min(chunk, g.width - c0)
            p = out_dir / f"{name}_r{r0}_c{c0}.tif"
            parts.append(p)
            if p.exists():
                continue
            x0, y1 = g.west + c0 * g.res, g.north - r0 * g.res
            print(f" - {name} chunk r{r0} c{c0}")
            r = _get(f"{EEA}/{service}/ImageServer/exportImage", params={
                "bbox": f"{x0},{y1 - h * g.res},{x0 + w * g.res},{y1}", "bboxSR": 32636, "imageSR": 32636,
                "size": f"{w},{h}", "format": "tiff", "pixelType": "U8",
                "interpolation": "RSP_NearestNeighbor", "compression": "LZ77", "f": "image"})
            if r.content[:2] not in (b"II", b"MM"):
                raise RuntimeError(f"{name}: service did not return a TIFF: {r.content[:200]!r}")
            p.write_bytes(r.content)
    vrt = out_dir / f"{name}.vrt"
    subprocess.run(["gdalbuildvrt", "-q", "-overwrite", str(vrt), *map(str, parts)], check=True)
    return vrt


def read_10m(vrt, nodata=255):
    g10 = habitat_grid().at(10)
    with rasterio.open(vrt) as src, WarpedVRT(src, crs=g10.crs, transform=g10.transform, width=g10.width,
                                              height=g10.height, resampling=Resampling.nearest,
                                              nodata=nodata) as v:
        return v.read(1)


# ------------------------------------------------------------------ CORINE
def fetch_corine() -> gpd.GeoDataFrame:
    out = RAW / "clc2018.gpkg"
    if not out.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        print(" - CORINE 2018 polygons (Cyprus)")
        w, s, e, n = config.load("region")["bbox_lonlat"]
        feats, off = [], 0
        while True:
            r = _get(f"{CLC}/query", params={
                "where": "1=1", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
                "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "Code_18",
                "outSR": 4326, "f": "geojson", "resultOffset": off, "resultRecordCount": 1000})
            page = r.json().get("features", [])
            feats += page
            off += len(page)
            if len(page) < 1000:
                break
        gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326").to_crs(
            config.load("region")["crs"]).to_file(out)
    return gpd.read_file(out)


# ------------------------------------------------------------------ SoilGrids
def fetch_soilgrids():
    """SoilGrids WCS coverages clipped to Cyprus (EPSG:4326, ~250 m)."""
    cfg = config.load("soil")["soilgrids"]
    w, s, e, n = config.load("region")["bbox_lonlat"]
    out_dir = RAW / "soilgrids"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for prop in cfg["properties"]:
        stats = ["mean"] + (["Q0.05", "Q0.95"] if prop in cfg["uncertainty"] else [])
        for d in cfg["depths"]:
            for st in stats:
                cov = f"{prop}_{d}_{st}"
                p = out_dir / f"{cov}.tif"
                files[cov] = p
                if p.exists():
                    continue
                print(f" - SoilGrids {cov}")
                r = _get(cfg["wcs"], params=[
                    ("map", f"/map/{prop}.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"),
                    ("REQUEST", "GetCoverage"), ("COVERAGEID", cov), ("FORMAT", "image/tiff"),
                    ("SUBSET", f"long({w},{e})"), ("SUBSET", f"lat({s},{n})"),
                    ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
                    ("OUTPUTCRS", "http://www.opengis.net/def/crs/EPSG/0/4326")], timeout=300)
                if r.content[:2] not in (b"II", b"MM"):
                    raise RuntimeError(f"SoilGrids {cov}: not a TIFF: {r.content[:200]!r}")
                p.write_bytes(r.content)
    return files


def soil_to_grid(path, g):
    """One SoilGrids coverage -> our 250 m UTM grid (bilinear). 0 = no data (sea) -> NaN."""
    with rasterio.open(path) as src:
        a = np.full((g.height, g.width), np.nan, "float32")
        from rasterio.warp import reproject
        reproject(src.read(1).astype("float32"), a, src_transform=src.transform, src_crs=src.crs,
                  src_nodata=0, dst_transform=g.transform, dst_crs=g.crs, dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
    return a


def depth_mean(files, prop, stat, g, cfg):
    t = np.array(cfg["thickness_mm"], float)
    layers = [soil_to_grid(files[f"{prop}_{d}_{stat}"], g) for d in cfg["depths"]]
    return sum(w * a for w, a in zip(t, layers)) / t.sum(), layers


def awc_layer(fc, wp, stones, thick_mm):
    """Available water (mm) of one soil layer: (field capacity - wilting point) x (1 - stones) x thickness.
    fc, wp, stones as volume shares (0-1)."""
    return np.clip(np.asarray(fc) - np.asarray(wp), 0, None) * (1 - np.nan_to_num(np.asarray(stones, float))) * thick_mm


def awc_mm(files, g, cfg, fc_stat="mean", wp_stat="mean"):
    """Available water capacity 0-30 cm (mm) = sum over depths of (FC - WP) x (1 - stones) x thickness."""
    total = np.zeros((g.height, g.width), "float32")
    for d, thick in zip(cfg["depths"], cfg["thickness_mm"]):
        fc = soil_to_grid(files[f"wv0033_{d}_{fc_stat}"], g) / 1000.0     # cm3/cm3
        wp = soil_to_grid(files[f"wv1500_{d}_{wp_stat}"], g) / 1000.0
        stones = soil_to_grid(files[f"cfvo_{d}_mean"], g) / 1000.0         # volume share
        total += awc_layer(fc, wp, stones, thick)
    return total


def drainage_class(sand_pct, clay_pct, dcfg):
    """1 = fast, 2 = medium, 3 = slow (0 = no data). [DRAFT] texture rule from config/soil.yaml."""
    out = np.full(sand_pct.shape, 2, "uint8")
    out[(sand_pct >= dcfg["fast_sand_pct"]) | (clay_pct < dcfg["fast_clay_below_pct"])] = 1
    out[clay_pct >= dcfg["slow_clay_pct"]] = 3
    out[~np.isfinite(sand_pct) | ~np.isfinite(clay_pct)] = 0
    return out


# ------------------------------------------------------------------ build
def main():
    g = habitat_grid()
    soil_cfg = config.load("soil")
    sg = soil_cfg["soilgrids"]
    layers = {}

    print("Tree cover density (10 m)")
    tcd = read_10m(fetch_eea_10m("GioLandPublic/HRL_TreeCoverDensity_2018", "tcd"))
    tcd = np.where(tcd <= 100, tcd, np.nan).astype("float32")              # 255 = outside / no data
    layers["tree_cover_pct"] = block_mean(tcd, 25)

    print("Grassland (10 m)")
    grs = read_10m(fetch_eea_10m("GioLandPublic/HRL_Grassland_2018", "grassland"))
    layers["grass_frac"] = block_mean(np.where(grs == 255, np.nan, (grs == 1).astype("float32")), 25)

    print("CORINE 2018")
    clc = fetch_corine()
    g25 = g.at(25)
    for band, codes in CLC_CLASSES.items():
        sel = clc[clc["Code_18"].astype(str).isin(codes)]
        r25 = rasterize(((geom, 1) for geom in sel.geometry), out_shape=(g25.height, g25.width),
                        transform=g25.transform, dtype="uint8") if len(sel) else np.zeros((g25.height, g25.width), "uint8")
        layers[band] = block_mean(r25.astype("float32"), 10)
    layers["clc_covered"] = block_mean(rasterize(((geom, 1) for geom in clc.geometry),
                                                 out_shape=(g25.height, g25.width), transform=g25.transform,
                                                 dtype="uint8").astype("float32"), 10)

    print("SoilGrids")
    files = fetch_soilgrids()
    layers["awc_mm"] = awc_mm(files, g, sg)
    layers["awc_q05_mm"] = awc_mm(files, g, sg, "Q0.05", "Q0.95")          # driest plausible
    layers["awc_q95_mm"] = awc_mm(files, g, sg, "Q0.95", "Q0.05")          # wettest plausible
    sand, _ = depth_mean(files, "sand", "mean", g, sg)
    clay, _ = depth_mean(files, "clay", "mean", g, sg)
    layers["sand_pct"], layers["clay_pct"] = sand / 10, clay / 10           # g/kg -> %
    ph, _ = depth_mean(files, "phh2o", "mean", g, sg)
    ph05, _ = depth_mean(files, "phh2o", "Q0.05", g, sg)
    ph95, _ = depth_mean(files, "phh2o", "Q0.95", g, sg)
    layers["ph"], layers["ph_q05"], layers["ph_q95"] = ph / 10, ph05 / 10, ph95 / 10
    soc, _ = depth_mean(files, "soc", "mean", g, sg)
    layers["soc_gkg"] = soc / 10                                            # dg/kg -> g/kg
    layers["drainage"] = drainage_class(layers["sand_pct"], layers["clay_pct"], soil_cfg["drainage"]).astype("float32")

    print("Geology: calcareous share")
    geo = gpd.read_file(config.RAW / "vectors.gpkg", layer="geology")
    calc = geo[geo["unit"].isin(set(soil_cfg["geology"]["calcareous_units"]))]
    r25 = rasterize(((geom, 1) for geom in calc.geometry), out_shape=(g25.height, g25.width),
                    transform=g25.transform, dtype="uint8")
    layers["calcareous_frac"] = block_mean(r25.astype("float32"), 10)

    out = config.PROCESSED / "habitat_v03_250m.tif"
    prof = dict(driver="GTiff", width=g.width, height=g.height, count=len(layers), dtype="float32",
                crs=g.crs, transform=g.transform, nodata=np.nan, compress="deflate", predictor=3, tiled=True)
    with rasterio.open(out, "w", **prof) as dst:
        for i, (name, a) in enumerate(layers.items(), start=1):
            dst.write(np.asarray(a, "float32"), i)
            dst.set_band_description(i, name)

    # A short report (forest squares only) + the Karpas check.
    with rasterio.open(config.PROCESSED / "habitat_250m.tif") as src:
        hab = {src.descriptions[i]: src.read(i + 1) for i in range(src.count)}
    forest = hab["forest_type"] > 0
    q = lambda a: [round(float(np.nanpercentile(a[forest], p)), 1) for p in (10, 50, 90)]
    from pyproj import Transformer
    lon, lat = g.cell_centres_lonlat()
    karpas = forest & (lon > 34.2)
    summ = {
        "forest_squares": int(forest.sum()),
        "tree_cover_pct_p10_p50_p90": q(layers["tree_cover_pct"]),
        "forest_squares_tree_cover_below_min": int((forest & (layers["tree_cover_pct"] < soil_cfg["habitat_v03"]["tree_cover_min_pct"])).sum()),
        "karpas_forest_squares": int(karpas.sum()),
        "karpas_tree_cover_p50": round(float(np.nanmedian(layers["tree_cover_pct"][karpas])), 1) if karpas.any() else None,
        "awc_mm_p10_p50_p90": q(layers["awc_mm"]),
        "ph_p10_p50_p90": q(layers["ph"]),
        "calcareous_share_of_forest": round(float(np.nanmean(layers["calcareous_frac"][forest])), 3),
        "corine_covered_share_of_forest": round(float(np.nanmean(layers["clc_covered"][forest])), 3),
        "burnt_corine_squares": int((layers["clc_burnt"] > 0.25).sum()),
    }
    (config.PROCESSED / "habitat_v03_summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
