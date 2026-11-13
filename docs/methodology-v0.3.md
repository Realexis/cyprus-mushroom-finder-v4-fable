# Methodology v0.3 — species engine (spec)

Saved from the user's v0.3 brief (sections 2 to 6), 2026-11-13. This is the spec the
`v0.3-species-engine` branch is built against. Every number in it is a **starting guess
from research**, to be calibrated later.

## 2. Goal and why the model is changing
Goal: an intelligent system that finds the best conditions for EACH species individually, because species have different needs. One shared engine, one profile per species. The map shows GROWING CONDITIONS only, never "mushrooms are here", never "edible" or "safe".

Faults in the current v1 score (from the methodology review):
1. Water is points, not a gate. The score is a weighted sum, so a spot with zero rain can still reach ~65/100. Every day currently scores 86-90.
2. One general score for very different species (early warm-rain species, cold winter species, spring burn species).
3. A snapshot, not a cycle. No memory of the season, no "spent after a flush".
4. The waiting time after rain is fixed in calendar days. Research says 7-10 days when soil is moist and mild, 15-20 days when dry or cool. Use degree-days.
5. Three water inputs (rain total 20%, rain pulse 15%, soil moisture 15%) overlap: 50% of the score is water counted up to three times.
6. Season x altitude is a hard-coded calendar that double-counts temperature and fails in odd years (2025-26: rain came late and cold).

## 3. The species engine

### 3.1 Architecture
- `species/` folder: one profile file per species (JSON or YAML). All numbers live there, never hard-coded in the engine.
- `engine/`: shared code that runs every profile on every 250 m square, for today + 7 forecast days.
- Outputs: one score layer per species per day + a summary JSON (top spots per species per day, with reasons).
- Keep the data layer separate so a live daily job (GitHub Actions + Open-Meteo) plugs in cleanly later.
- Weather: use the Open-Meteo forecast and historical APIs (free, no key) where possible, including soil temperature and soil moisture. If the network is unavailable, keep the sample data and build against it.

### 3.2 What the engine computes, per square, per species, per day
1. Habitat fit (0 to 1): weighted host-tree strength, minimum tree cover, soft altitude range, rock type, soil fit (3.9), burn history.
2. Soil-water bucket: rain fills it; evaporation empties it (simple method, e.g. Hargreaves), faster on sunny south slopes, slower in shade. Capacity and drainage per square come from the soil layer (3.9): sandy or stony soil drains fast, clay and organic-rich soil hold water. This REPLACES the three overlapping water inputs.
3. Soil temperature: from Open-Meteo, corrected for altitude with a lapse rate.
4. Cycle state machine: Dormant -> Primed -> Triggered (waiting, counting degree-days) -> Window open -> Spent -> Recovering. Trigger = the bucket passes the species threshold. The window ends when soil dries, frost hits, or the window length runs out. Spent squares need a new trigger after the recovery time.
5. Species score = habitat fit x water fit x temperature fit x cycle-state factor, times a soft season prior (0.5 to 1). MULTIPLY, never a weighted sum: near-zero water must give a near-zero score.
6. General map = the best score among the species currently shown.

### 3.3 Six species groups with different rules
| Group | Species | What drives it | Reaction speed |
|---|---|---|---|
| Pine partners | red pine mushroom, bloody milk cap, white brittlegill, matsutake, slippery Jack, chanterelle | soaking rain + right soil temperature; matsutake also a temperature-drop cue | days to weeks |
| Oak partners | bronze bolete/cep, yellow and red cracked boletes | rain on evergreen oaks (golden oak, kermes oak), warmer end | days to weeks |
| Litter and field recyclers | wood blewit, shaggy ink cap, field mushroom | rain + cool weather, not tied to a host tree | long season into winter |
| Fennel-root | fennel king oyster | fields with giant fennel; rain and humidity weigh more than temperature | autumn to spring |
| Burn species | morels | burned ground (best where most of the surface burned) + spring soil warming (~10 C) | one spring after a fire |
| Underground | desert truffles | rock-rose scrub; spring crop driven by accumulated Oct-Dec rain | months of memory |

Research notes behind this: partner fungi and litter recyclers track weather closely, wood-rotting fungi much less (Spanish pine forest study). Late-summer to early-autumn rain pulses drove Spain's record yields. Last year's forest greenness (NDVI) was the best single yield predictor in Spanish pine forests: add it later as a habitat bonus. Medium tree density beats very open or very dense stands. Young pine stands (11-20 years) gave the highest red pine mushroom yields.

### 3.4 Profile fields (every profile has all of these)
group, host_trees (name: weight 0-1), altitude_range (soft), trigger_mm, wait_degree_days (+ base temperature), soil_temp_window (min, best, max), extra_cues, window_length_days, recovery_days, season_prior (by month), tier (key | more), rare (true/false), confidence (low | medium), local_name (mark "to confirm"), english_name, latin_name, lookalikes (2-3 specific to this species), soil_pref (ph: acid | neutral | alkaline | any | unknown; texture preference; weight as a soft multiplier 0.8-1.0), sources.

Example, red pine mushroom (starting guesses):
group pine partner; host trees Calabrian pine 1.0, black pine 0.8, golden oak 0.5, kermes oak 0.4; altitude sea level to 1,950 m; trigger about 20 mm soaking rain over 1-3 days; wait calibrated from the 7-20 day rule; temperature mild, frost stops it; extra cue young stands (11-20 years) bonus; window about 1-2 weeks; season prior Oct-Jan, high ground first; tier key; confidence medium.

Every number is a guess from research. Write a comment in each profile saying so.

### 3.5 Species list and tiers
| Species | Latin | Local name (to confirm) | Tier | Habitat | Season | Group | Confidence |
|---|---|---|---|---|---|---|---|
| Red pine mushroom | Lactarius deliciosus | Kokkinomanitaro | key | pine, oaks | Oct-Jan | pine partner | medium |
| Bloody milk cap | Lactarius sanguifluus | Gematas | key | black pine above 1,200 m | Sep-Oct | pine partner | medium |
| White brittlegill | Russula delica | Aspromanitaro | key | all forest | Sep-Oct (warm spells) | pine partner | medium |
| Matsutake | Tricholoma caligatum | Imero | key | pine, golden oak | Nov-Jan | pine partner + cold cue | low |
| Slippery Jack | Suillus luteus | Lartias | key | pine | Oct-Jan | pine partner | medium |
| Fennel king oyster | Pleurotus eryngii var. ferulae | - | key | giant fennel fields | autumn-spring | fennel-root | low |
| Morels | Morchella esculenta / elata | Arnaoui | key | burned ground, broadleaf | Mar-Apr | burn | low |
| Bronze bolete / cep | Boletus aereus / edulis | - | more | golden and kermes oak | autumn, not every year | oak partner | low |
| Yellow and red cracked boletes | Xerocomus subtomentosus / chrysenteron group | - | more | oaks | autumn | oak partner | low |
| Wood blewit | Lepista nuda | - | more | all forest | autumn-winter | litter recycler | medium |
| Shaggy ink cap | Coprinus comatus | - | more | meadows, roadsides | Dec-Feb | field recycler | medium |
| Field mushroom | Agaricus campestris | - | more | grassland | winter-spring | field recycler | medium |
| Chanterelle | Cantharellus cibarius / subpruinosus | - | more, rare | pine | autumn-winter | pine partner | low |
| Desert truffle | Terfezia | - | more, rare | rock-rose scrub | spring | underground | low |

Do NOT add: Volvariella gloiocephala (too close to deadly white Amanitas), Caesar's mushroom (not confirmed in Cyprus).

### 3.6 Habitat layers
- Fix the forest filter: the current #1 spot is the Karpas tip, mostly scrub. Require a minimum tree cover (Copernicus Tree Cover Density) for tree-partner species.
- Use the Dept of Forests tree species map (Cyprus INSPIRE GeoPortal) if obtainable; otherwise keep the altitude + forest-type rule and flag it as approximate.
- Add: evergreen-oak layer; fields/grassland layer (CORINE) for fennel king oyster and field recyclers; rock-rose scrub layer (CORINE sclerophyllous vegetation) for desert truffles; burn scars with fire year (EFFIS) for morels and for young-pine-stand age.
- Nature reserves stay CLOSED (score 0).
- The north: ask the user before deciding whether northern areas appear in "Best spots".

### 3.7 Confidence and labels
- Show words, not "90": Poor / Fair / Good / Very good, plus window text like "Window open, about 5 more days" or "Opens in about 3 days".
- Forecast confidence = how much of the score depends on rain that has NOT fallen yet. A window driven by rain that already fell is fairly sure even 6 days ahead.

### 3.8 Getting smarter later (do not build yet, just leave room)
1. Calibrate timing per species with dated iNaturalist/GBIF Cyprus records.
2. Learn from our trip log, including empty trips. Species in the same group share what they learn, so rare species borrow from their group until they have their own data.
3. After about 30 finds of one species, fit its own thresholds.

### 3.9 Soil layer (new in v0.3)
Why: soil decides how long rain stays available to the fungus, and some species prefer acid or alkaline ground. In Mediterranean holm oak forests, soil pH, organic matter and sand content shaped which fungi fruited, and soil water retention is set mainly by texture, structure and organic matter (Ponce et al. 2022). Desert truffle species split by soil: some on acid soils, others on alkaline.

What to build, one fixed 250 m soil layer:
- Available water capacity: from SoilGrids water content at field capacity (wv0033) and wilting point (wv1500), corrected for coarse fragments (cfvo). Average the 0-30 cm depths. This sets each square's bucket size.
- Drainage speed: from sand and clay content.
- Soil pH (phh2o) and organic carbon (soc) for species preferences.
- Calcareous vs not: from the geological map (limestone, chalk, marl = calcareous; Troodos igneous rocks = not). If the user's Clay Atlas project has Geochemical Atlas grids (e.g. calcium), ask for them and use them to refine this.

Data sources, in priority order:
1. SoilGrids 2.0 by ISRIC: 250 m, free, CC BY 4.0. Its REST API has been paused, so use the WCS service or the cloud-optimized GeoTIFFs, clipped to Cyprus. Also download the Q05 and Q95 uncertainty layers.
2. Geological map of Cyprus (Geological Survey Dept, free on ESDAC) for calcareous vs igneous.
3. Later, if obtainable: the Dept of Agriculture soil map ("The Soils of Cyprus", 2022) and the Cyprus Institute digital soil map of soil types and texture. Ask the user before requesting any data.

Do NOT use LUCAS points: Cyprus has fewer than 70 samples, too sparse.

How to use it (keep it gentle):
- Soil is a SOFT modifier (0.8 to 1.0) and sets the bucket size. It is never a yes/no filter.
- SoilGrids is a machine-learning prediction with few soil profiles from Cyprus. Where its uncertainty band is wide, pull the soil effect towards neutral (1.0).
- Start every species' soil_pref as "unknown" except desert truffles (record that pH matters, value to confirm). Learn the rest from finds later.
- Add a "Soil" view in the layer switcher (water-holding capacity, pH), and show "soil holds water: well / average / poorly" in the "Why this score" panel.

## 4. Site feedback to fix (UX)
1. Species picker: key species by default; a "Show more species" toggle reveals the More tier; rare ones get a small "rare" tag.
2. Species list and cards: lead with the common name (and local Greek name when confirmed), Latin name smaller underneath. Remove the big red "Deadly and toxic lookalikes, learn these first" block from the top of the list. Do NOT lead cards with warnings.
3. Card order: photo -> names -> "Conditions for this species now" (state + best areas) -> where and when -> a compact "Don't confuse with" row of the 2-3 lookalikes specific to THIS species (tap to expand). Replace the generic list of 10 lookalikes shown on every card.
4. Keep the one-line safety bar and the Emergency button exactly as they are.
5. Missing photos (bloody milk cap is blank): add a neutral placeholder, or properly licensed images with credits. Never use an image without a clear licence.
6. The species-list tooltip covers card content. Move it or show it on long-press only.
7. Day buttons: show the word label and a small bar instead of a number.
8. Best spots: per-species reasons, e.g. "window open 4 more days - soaking rain 12 days ago".
9. Desktop: move the floating "No rakes" box into the panel, as on mobile.
10. Label the crossed-out location button.
11. Mobile: on load, fit the whole island above the bottom panel (the Karpas tip was cut off).

## 4b. Rewrite the "About the data" panel
Replace the current "About the data" content so it explains the v0.3 method clearly. Use the text below as the starting copy (wording may be tightened, but keep every point). Format: short sections with headings, one idea per line, bold key words, a small diagram or icons for the formula. It must work at 375 px. Every number shown must match the real values in the code and profiles; update the copy if a value changes.

--- START OF COPY ---
About the data

What this map shows
Where the growing conditions are right for each mushroom species, today and for the next 7 days. It does not show where mushrooms are, and it never says a mushroom is safe to eat.

Each species has its own needs
Pine mushrooms, oak boletes, field mushrooms, morels and desert truffles all react to different trees, rain, warmth and ground. So the map runs a separate check for every species. The general map shows the best result among the species you have switched on.

The score in one line
Conditions = habitat x water x temperature x mushroom clock
If any one of these is poor, the result is poor. Plenty of rain cannot make up for the wrong trees, and perfect trees cannot make up for dry ground.

1. Habitat: the right place
- Partner trees: most edible species live joined to the roots of certain trees (pine, golden oak, kermes oak). No partner tree, no mushroom.
- Tree cover, altitude, rock type and past fires.
- Soil: a gentle nudge for species that prefer acid or alkaline ground.

2. Water: is the ground wet enough?
Every 250 m square has a water "bucket". Rain fills it. Sun and wind empty it, faster on sunny south slopes, slower in shade.
The soil sets the bucket size:
- Clay and rich soil hold water longer, so good conditions last more days.
- Sandy or stony soil drains fast, so the window closes sooner.
The same rain can give two different results on two different slopes.

3. Temperature: not too hot, not too cold
Each species has its own comfortable soil temperature. Frost stops most of them.

4. The mushroom clock
Mushrooms do not appear the day it rains. After a soaking rain, the clock starts. Warm days make it run faster, cold days slower. When it runs out, the window opens for about one to two weeks. After a big flush, the ground needs a new soaking rain before the next one.

How sure is the forecast?
- "Sure": the window depends on rain that has already fallen.
- "Likely" or "unsure": it depends on rain that is only forecast.

Where the data comes from
- Weather: Open-Meteo (rain, temperature, soil temperature, soil moisture), updated daily.
- Terrain: Copernicus elevation model (slope, sun and shade).
- Forests: Copernicus forest type and tree cover maps.
- Soil: SoilGrids by ISRIC (water holding, texture, pH), plus the Geological Map of Cyprus.
- Burned areas: EFFIS fire maps.
- Species needs: published research from Cyprus and other Mediterranean forests.

Honest limits
- These are best estimates. Species numbers are starting guesses from research and will improve as we log real trips.
- Rain is estimated per area, not per slope. A local storm can be missed.
- The soil data is a computer estimate and Cyprus has few soil samples. Where it is unsure, soil has no effect on the result.
- Mushrooms are patchy. A "very good" square can still be empty.

Nature reserves are closed to picking and always shown as closed.

Conditions only. Never eat a wild mushroom based on this map, an app or an AI.
--- END OF COPY ---

Also: list the full data credits and licences (Open-Meteo CC BY 4.0, Copernicus, SoilGrids CC BY 4.0, map tiles) at the bottom of this panel.

## 5. Testing
- Unit tests for the engine: bucket, degree-days, state machine, multiplied score (zero water must give a near-zero score).
- Backtest the 2025-26 season with historical weather. The press reported a poor season (rain came late and cold). If the model says "great", find out why and report it.
- Check that scores now spread across days and areas instead of bunching at the top.
- Compare each key species' "window open" dates with dated iNaturalist/GBIF Cyprus records if available. Report matches and misses.

## 6. Rules
- Never use the words "edible", "safe" or "good to eat" next to a species or a map spot.
- Never remove or weaken the safety bar or the Emergency button.
- Do not invent data or species facts. Mark every guess as a guess.
- Accessibility: WCAG AA contrast, tap targets of at least 44 px, keyboard reachable, visible focus.
- Dyslexia-friendly UI text: short lines, plain words.
- One small commit per step on `v0.3-species-engine`, clear messages.
