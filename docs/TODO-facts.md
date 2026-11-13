# Facts we still need

These values are **not in the brief**. The code runs with a **[DRAFT]** placeholder
(see `config/scoring.yaml`). Nothing here is presented to users as fact.

## Habitat (Phase 1)
| # | What | Draft value now | Where |
|---|---|---|---|
| H1 | Share of a 250 m cell that must be forest | 25% | `habitat.forest_min_fraction` |
| H2 | **Mid / low altitude boundary** | 600 m | `habitat.altitude_bands.mid_min_m` |
| H3 | Does **serpentinite** count as "Troodos igneous rock" for golden oak? | yes | `habitat.trees.troodos_igneous_units` |
| H4 | Share of a cell that must be igneous rock | 50% | `habitat.trees.igneous_min_fraction` |
| H5 | **Shade recipe**: weights of slope facing / valley / low sun | equal thirds | `habitat.shade.weights` |
| H6 | Valley index radius and depth for full effect | 500 m, 30 m | `habitat.shade.valley_*` |
| H7 | Autumn sun date used for hillshade | 31 Oct, 08-16 h | `habitat.shade.autumn_sun_*` |

## Score (Phase 2+)
| # | What | Draft value now |
|---|---|---|
| S1 | Frost penalty size | -0.1 per frost day |
| S2 | Soil moisture percentile mapping | 0 at p20 -> 1 at p80 |
| S3 | **Season x altitude table** as numbers | drafted from the brief's words |
| S4 | Mushroom clock shift for high/cool cells | 0 days |
| S5 | Russula delica "warm spells" rule | none yet |
| S6 | Soaking event must end on a wet day (≥ 1 mm) | 1 mm (standard wet-day definition) |
| S7 | ~~Should "Other broadleaf" count as habitat in the general map?~~ | **Answered 2026-11-12: no, except for morels.** `score.general_map_trees: [1, 2, 3]` |
| S8 | Soil "normal" uses only ONE season (Oct 2025-Jan 2026) | add 2 more seasons, one per day |
| S9 | *Russula delica* is "all forest" in the brief. Should "Other broadleaf" count for it? (S7 answer kept it out) | not counted |

## Species and lookalikes (Phase 5)
| # | What | Draft value now | Where |
|---|---|---|---|
| L1 | **Which lookalikes go with which species** (the brief lists 10, no pairing) | every card shows all 10 | `config/lookalikes.yaml` |
| L2 | Severity "deadly" for *Amanita verna* and *A. virosa* (brief only says "deadly/toxic") | deadly (general mycology references) | `config/lookalikes.yaml` |
| L3 | Taxon for the 'pink "sickener" Russula' | *Russula emetica* | `config/lookalikes.yaml` |
| L4 | Morels = deciduous trees. Golden oak is evergreen, so only "Other broadleaf" counts; that class mixes deciduous and evergreen trees | Other broadleaf, mid + high | `config/species.yaml` |
| F1 | **Species field notes** ("What to look for", "Where to look", "Leave it alone if") were researched from public sources on 2026-11-12 (Cyprus Dept. of Forests, KYKPEE, Wikipedia, First Nature…). User chose to show them, labelled "not checked by an expert". **Have every line checked by the Cyprus Mycological Association** | shown, labelled | `web/src/ui/species.ts` (FIELD) |
| F2 | Woolly milk cap (*Lactarius torminosus*, poisonous, grows in Cyprus per sources) is not in the 10-lookalike list | add to `config/lookalikes.yaml`? | `config/lookalikes.yaml` |
| F3 | Which *Suillus* is "lartias"? Cyprus Dept. of Forests lists *S. collinitus* and *S. granulatus*, not *S. luteus* | to confirm | `config/species.yaml` |
| F4 | Cyprus morels: *M. arbutiphila* and *M. disparilis* were described from Cyprus (2016); the names *M. esculenta / elata* may need updating | to confirm | `config/species.yaml` |
| D8 | Kermes oak map (brief: red pine mushroom also with kermes oak) | not mapped, not counted | `config/species.yaml` |
| S10 | Species scores differ only by trees, altitude and season (brief rule), so species sharing a habitat get the same number. Species-specific rain/temperature rules? | none (not in the brief) | `config/species.yaml` |
| S11 | **More target species**: public Cyprus records are too few (max ~15 per mushroom on GBIF) to derive trees or seasons | waiting for a source (user / Cyprus Mycological Association) | `config/species.yaml` |
| P1 | ~~50 m hotspot zoom private?~~ **Answered 2026-11-12: the public site shows the 250 m squares and the hotspot zoom** (overrides the brief's ~2 km rule; finds stay private). 50 m shade is now one fixed island-wide file, `web/public/tiles/shade50.pmtiles` (`shroomy.export.shade50`). **Before merging to `main`, upload it to the `static-v1` release** (the daily robot copies `*.pmtiles` from there) | public | `pipeline/shroomy/export/shade50.py` |

## v0.3 habitat + soil (step 3)
| # | What | Draft value now | Where |
|---|---|---|---|
| V1 | Minimum tree cover for tree-partner species | 30% | `config/soil.yaml -> habitat_v03` |
| V2 | **Formation -> rock grouping** for "calcareous" (Lefkara, Pakhna, Nicosia, Lapithos, Kyrenia limestones…) | see list | `config/soil.yaml -> geology` |
| V3 | Drainage classes from texture (fast: sand ≥ 60% or clay < 15%; slow: clay ≥ 35%) | rule of thumb | `config/soil.yaml -> drainage` |
| V4 | **Burn scars with fire year (EFFIS)**: services did not answer on 2026-11-13. Using CORINE 2018 "burnt areas" (no year) meanwhile | to retry | `pipeline/shroomy/habitat/v03.py` |
| V5 | Kermes oak (Quercus coccifera) has no map. Golden oak = broadleaf on Troodos rock (approximate) | approximate | habitat layer |
| V6 | Dept of Forests tree-species map (INSPIRE) not obtained; tree zones stay rule-based (approximate) | approximate | habitat layer |
| V7 | Clay Atlas geochemical grids (e.g. calcium) could refine "calcareous" | ask the user | — |

## v0.3 engine (step 4) — settings in `config/engine.yaml`, all guesses to calibrate in the backtest

| ID | Question | Now | Where |
|---|---|---|---|
| E1 | Bucket fill on the first day of a run (spin-up) | 0.3 | `bucket.start_fill` |
| E2 | Smallest bucket | 10 mm | `bucket.capacity_min_mm` |
| E3 | Canopy catches the first mm of rain | 1.0 mm/day | `bucket.interception_mm` |
| E4 | Forest-floor evaporation vs open grass | 0.7 | `bucket.crop_factor` |
| E5 | Sunny vs shady slope evaporation | 1.2 / 0.8 | `bucket.sunny_k`, `shade_k` |
| E6 | Drainage above 70% full, per day | fast 0.30, medium 0.15, slow 0.05 | `bucket.drain_*` |
| E7 | Bucket fill for zero / full water fit | 0.15 / 0.60 | `water_fit` |
| E8 | Soil temperature = air running mean, lag | 4 days (until P2) | `soil_temperature.proxy_days` |
| E9 | Trigger needs bucket 50% full; wait cancelled / window closed below 15% | 0.5 / 0.15 | `cycle` |
| E10 | Window cut short by dry soil or frost goes back to Primed (not Spent); Spent = first 3 recovery days. **Audit step 3:** species with `recovery_days: 0` go on as a late window while wet; once a window has opened since 1 Sep, new soaking rain re-opens it after 2 days `[LOI19]` | our reading of the spec + LOI19 | `cycle.spent_days`, `cycle.rewet_wait_days` |
| E11 | Score multiplier per cycle state | dormant 0.05, primed 0.2, triggered 0.3-0.8, open 1, **late window 0.6 [GUESS]**, spent 0.1, recovering 0.2 | `cycle.factor` |
| E12 | Soft edges: tree cover 15 points, altitude 150 m | | `habitat` |
| E13 | Burnt share for full morel habitat | 0.5 | `habitat.burn_full_at_frac` |
| E14 | pH acid below 6.5, alkaline above 7.5, ramp 1 unit | | `habitat.ph_*` |
| P2 | **Fetch Open-Meteo soil temperature** (`soil_temperature_0_to_7cm`). Check the call budget first | proxy from air temperature | `config/weather.yaml` |

| L5 | **Species-specific lookalikes** for each profile (spec wants 2-3, sourced). Now: red pine mushroom and bloody milk cap list only *Lactarius chrysorrheus* (the brief's milk-colour note; for the bloody milk cap it is our guess) | 1 each | `species/*.yaml` |
| S12 | Profile numbers for red pine mushroom and bloody milk cap (wait **150** degree-days above 4 C [LOI19 + backtest weather, audit step 2; base 4 C a guess], recovery **0** [LOI19, step 3]; soil 3-24 C best 8-18, window 10 days, season edges) are guesses | guesses | `species/lde.yaml`, `lsa.yaml` |
| E15 | Land cover counts from a 20% share of the square, full weight from 50% | 0.2 / 0.5 | `config/engine.yaml` `habitat.land_cover_*` |
| S13 | Step 6 profiles (12 species): most numbers are group defaults copied from the red pine mushroom, marked [GROUP] or [GUESS] in each file. Not modelled yet: warm spells (white brittlegill), cold cue (matsutake), humidity (fennel king oyster), fire year (morels), Oct-Dec rain memory (desert truffle) | guesses | `species/*.yaml` |
| S14 | Fennel king oyster: no giant fennel map. Fields and grassland stand in at half weight. No photo with an allowed licence on iNaturalist yet | stand-in | `species/pfe.yaml` |
| S15 | Desert truffles: which soil pH (spec: "pH matters, value to confirm") | unknown | `species/ter.yaml` |
| E16 | Forecast confidence from rain dependence: sure under 25% of the score needing forecast rain, likely up to 60%, else unsure. Temperature forecast errors are not counted yet | 0.25 / 0.6 | `config/engine.yaml` `confidence` |

Bucket size uses "blend by certainty" (user, 2026-11-13). SoilGrids is so unsure in Cyprus that today every forest bucket is the island median (26.9 mm); drainage class and slope still differ.

## Data and legal
| # | What | Status |
|---|---|---|
| D1 | **Geology licence** (Geological Survey Dept. via DLS INSPIRE) | unknown. Used internally only. Ask INSPIRE@dls.moi.gov.cy |
| D2 | Natura 2000 licence record | expected CC BY 4.0, record not read yet |
| D3 | **Areas not under Republic control** (north): picking rules, reserves | no data. Forest is mapped; legal notes do not apply there |
| D4 | British Sovereign Base Areas: picking rules | unknown |
| D5 | Burned ground source for morels | not chosen |
| D6 | Rare species list for the public view | not given |
| D7 | Local Greek names (except kokkinomanitaro) | "to confirm with the Cyprus Mycological Association" |

## Audit steps (V4 Fable feedback branch, 2026-11-13)
| # | What | Now | Where |
|---|---|---|---|
| A1 | Wait for the first flush: 150 degree-days above 4 C for forest and fennel species `[LOI19 + backtest weather]`. Shaggy ink cap and field mushroom kept at 72 (fast recyclers, no source). Morels and desert truffle kept at 72: LOI19 is an autumn woodland rule | 150 / 72 | `species/*.yaml` |
| A2 | Late window factor (open past its full length, soil still wet) | 0.6 [GUESS] | `engine.yaml cycle.factor.late_open` |
| A3 | Morels 30 and desert truffle 60 recovery days kept: nothing found either way | [GUESS] | `species/mor.yaml`, `ter.yaml` |
