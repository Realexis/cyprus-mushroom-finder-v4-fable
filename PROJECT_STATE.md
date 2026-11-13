# Project state — Cyprus Mushroom Finder (branch `v0.3-species-engine`, 2026-11-13)

The site shows **growing conditions** for wild mushrooms in Cyprus forests.
Never "mushrooms are here", never anything about eating.

## Versions and branches
| What | Where |
|---|---|
| **Live site (v0.2)** | https://realexis.github.io/cyprus-mushroom-finder/ — `gh-pages`, rebuilt **daily 04:00 UTC from `main`** (`.github/workflows/daily.yml`). `main` = `a658098` (Phase 5 + ux-v2 + phone panel). Backups: `live-backup-phase4`, `live-backup-2026-11-13`. |
| **Test copy** | https://realexis.github.io/cyprus-mushroom-finder-preview/ — built by hand from `dev` (= `ux-v2`). |
| **This branch (v0.3)** | `v0.3-species-engine`, from `main`. Version 0.3.0, "v0.3 preview" badge (`web/src/version.ts`). Local preview: `ux-v2-web`, port 5205. Spec: `docs/methodology-v0.3.md`. |
| Side branch | `simple-prototype` — the simple-redesign test page. |

## The data is real (not sample)
- **Weather:** Open-Meteo, model **ECMWF IFS (~9 km)**, ~1,159 points over the island. Daily: rain, mean/min/max temperature, humidity. Hourly → daily: **soil moisture 0–7 cm**. **Not fetched yet: soil temperature.** 30 past days + 8 forecast days. Rolling history in `data/processed/weather/history.npz` (daily robot keeps it in the Actions cache). Soil "normal" from **one** past season (2025-26), `soil_climatology.npz`.
- Free tier budget: 10,000 calls/day (we cap at 8,000). A location costs 1 call per 14 days × 10 variables.
- The **data layer is separate**: the Python pipeline writes static files; the website only reads them.

## Where the files live
- **Daily outputs** → `web/public/data/` (gitignored, published): `cells.pmtiles` (250 m squares: score per day, base score, tree, band, clock), `cells_info.bin` (factors + inputs per square/day), `cells_road.bin` (drive-there points), `hexes.geojson` + `spots.json` (~2 km zones), `rain.geojson`, `reserves.geojson`, `hotspot_zones.json`, `meta.json`, `summary.json`.
- **Fixed map files** → `web/public/tiles/` (gitignored; for the robot they come from the `static-v1` release): `basemap.pmtiles` (Protomaps OSM), `terrain.pmtiles` (Copernicus DEM), `shade50.pmtiles` (island-wide 50 m shade).
- **Pipeline data** → `data/` (gitignored, private): `processed/habitat_250m.tif`, `dem_25m.tif`, weather runs, score rasters; `raw/` downloads (DEM tiles, forest type 10 m, reserves, Natura 2000, geology, OSM roads, iNaturalist/GBIF caches).
- **Settings** → `config/` (`scoring.yaml` every weight/threshold, `species.yaml`, `lookalikes.yaml`, `sources.yaml`, `weather.yaml`, `region.yaml`). Open facts: `docs/TODO-facts.md`.

## Layers that exist (250 m habitat raster `habitat_250m.tif`)
`habitat_filter` (open forest, reserves closed) · `forest_type` (conifer/broadleaf, ≥25% of the square) · `likely_tree` (Calabrian pine / black pine >1,200 m on igneous rock / golden oak on igneous rock / other broadleaf / cedar zone) · `altitude_band` (low <600 m [draft] / mid / high >1,200 m) · `reserve_id` · `natura2000` · `conifer_fraction`, `broadleaf_fraction` · `igneous_fraction` (Troodos rocks, geology map) · `elevation_m`, `slope_deg`, `aspect_deg`, `tpi_m` · `facing_score`, `valley_score`, `low_sun_score` → `shade_score` · `land_fraction`.
Plus: 50 m shade (fixed), OSM roads/tracks, nature reserves, Natura 2000.

**Missing for v0.3:** tree cover density, evergreen-oak / kermes-oak layer, CORINE fields/grassland and sclerophyllous scrub, EFFIS burn scars with fire year, SoilGrids soil layer, calcareous-rock flag, a real tree-species map.

## How the score is computed today (v1, weighted sum)
Per 250 m forest square, per day (today + 7):
`score = habitat_filter × (0.20 rain_30d + 0.15 rain_pulse + 0.25 temperature + 0.15 soil_moisture + 0.15 season×altitude + 0.10 shade) × 100`
- rain_30d: 0 below 20 mm → 1 at 80 mm · rain_pulse: biggest 3-day sum 7–20 days ago, 0 below 10 mm → 1 at 25 mm
- temperature: 7-day mean, lapse-rate corrected (−6.5 °C/km), trapezoid 3/8/18/24 °C, −0.1 per frost day [draft]
- soil_moisture: percentile vs the one-season normal, 0 at p20 → 1 at p80 [draft]
- season×altitude: month × band table [draft] · shade: fixed terrain score
- General map: only partner trees (Calabrian pine, black pine, golden oak) — user decision S7.
- Species filters: same sum, only the trees/altitude bands and season months change (`config/species.yaml`).
- Mushroom clock: days since the last ≥20 mm soaking rain (window +7 → +20 days, fixed calendar days).
- Public zones (~2 km H3) = mean of their squares; `summary.json` lists the top zones per day/species.

**Known weaknesses (from the v0.3 review):** water counted three times (50% of the weight); a weighted sum lets a dry square still score ~65; all species share one formula; no season memory or "spent after a flush"; fixed calendar wait instead of degree-days; season×altitude calendar double-counts temperature; scores bunch at 86–90; the #1 zone (Karpas tip) is mostly scrub because the forest filter has no tree-cover minimum.

## Website (Vite + TypeScript + MapLibre 6 + PMTiles)
`web/src/main.ts` start-up, map, clicks · `map/layers.ts` map layers + 3D · `map/files.ts` published `*.pmtiles.zip` names · `ui/controls.ts` side panel / phone sheet (min / peek / full) · `ui/spot.ts` zone panel · `ui/species.ts` species explorer · `ui/legend.ts` colour key · `ui/guide.ts`, `tips.ts`, `safety.ts` · `version.ts`.
Build: `npm run build` (wording check bans "edible", "safe", "good to eat", "find X here"; files renamed for GitHub Pages).

## Tests
`cd pipeline && uv run pytest` — 73 tests (factors, clock, habitat rules, species rules, roads, terrain, history).

## Open questions
See `docs/TODO-facts.md` (drafts H1–H7, S1–S11, L1–L4, F1–F4, D1–D8, P1).
