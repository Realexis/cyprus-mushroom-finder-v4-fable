# Backtest log: V4 Fable feedback

Branch `v4-fable-feedback`. Each step of the audit directions (`DIRECTIONS-V4.md`, prediction audit,
2026-11-13) is tested here on the **same weather**, so old and new can be compared.

Run: `cd pipeline && uv run python -m shroomy.backtest --season <season> --label <name>`.
Numbers: `data/processed/backtest/backtest_<name>.json` (not in git).

## How we score the model now (step 1)

- **Find events, not records.** Same date and same place (about 1 km) = one find.
  The 23 morel records of 28 Feb 2026 are **one** find.
- **Search by genus**, because Cyprus observers rarely use exact species names:
  *Suillus* → slippery Jack, *Lactarius* → red pine mushroom (Cistus milk caps left out),
  *Morchella* → morels, *Pleurotus eryngii* → fennel king oyster, *Coprinus comatus* → shaggy ink cap,
  *Russula delica* and subgenus *Brevipes* → white brittlegill.
- **Weak (reported apart):** *Agaricus* (any species) → field mushroom, and *Russula* named only to genus.
- **Hit** = a window is open within 5 km on the find day.
- **Base rate** = the share of all season days with a window open within 5 km of that find.
  A model that says "open" every day would hit everything. **The gap between hit and base rate is the real result.**
- **Offset** = days from the find to the nearest open window: 0 open, −N closed N days before, +N opened N days later.

**Be honest:** a few dozen find events cannot calibrate 14 species. They can catch a wrong clock.

## Results

### Baseline: the branch as it was (`f455bda`), 2025-26, Sep-Feb weather

| | Find events | Hit | Base rate | Gap |
|---|---|---|---|---|
| Species-level | 10 | **0 %** | 16 % | −16 % |
| Genus only (weak) | 7 | 14 % | 15 % | −1 % |

- Slippery Jack finds (2 Dec, 27 Dec ×2, 10 Jan, 28 Feb): **all missed**. On 27 Dec the windows
  had **closed 3-6 days before** and the squares were "recovering".
- Shaggy ink cap (11 Jan, 19 Feb), fennel king oyster (25 Jan, 12 Feb), red pine (29 Jan): all missed,
  most in "triggered" or "recovering".
- Morels, 28 Feb (Karpas): the nearest morel habitat is **126 km** away (only burnt squares count).
- This file stops at 28 Feb, so March-April finds are not tested yet.

### Steps 2+3: wait about 19 days, no lock-out (same Sep-Feb weather)

| | Find events | Hit | Base rate | Gap |
|---|---|---|---|---|
| Species-level | 10 | **90 %** (was 0 %) | 37 % (was 16 %) | **+53 %** (was −16 %) |
| Genus only (weak) | 7 | 57 % (was 14 %) | 38 % | +19 % |

- **Dry autumn still zero.** September to November 2025: 0 % open for every species.
- **First windows later.** Red pine mushroom: first open squares 14 Dec (was 7 Dec), 28 % open on 26 Dec.
  The 18-20 day field rule (LOI19) from 7 Dec gives about 26 Dec.
- **No January gap.** Red pine open share by month: Dec 11 %, Jan 63 %, Feb 88 % (was 25 %, 2 %, 33 %).
- **Finds now inside windows:** slippery Jack 27 Dec (×2), 10 Jan, 28 Feb; red pine 29 Jan; shaggy ink cap
  11 Jan, 19 Feb; fennel king oyster 25 Jan, 12 Feb.
- **Still missed:** slippery Jack on 2 Dec (Troodos, before the first island-wide soaking rain).
  Morels 28 Feb: no morel habitat within 126 km (step 8).
- **Honest note:** the base rate rose too. Once wet, the winter stays open almost everywhere
  (shaggy ink cap 96-99 % in Jan-Feb). The gap, not the hit rate, is the result.

### Step 4: longer memory (option B, keep more history)

- The history now keeps **240 days** (was 75). The engine runs from **1 September** of the season,
  or as far back as the history has unbroken observed days. The map still shows today + 7 days.
- A run that starts in September starts with an **empty bucket** (was 30 % full).
- **Check (Fable):** a run started 31 days before the day, against a run from 1 September,
  same 2025-26 weather. Share of squares in the **same state** on that day:

| Day | Bucket (median, long / short) | Red pine: same state | Red pine open, long / short |
|---|---|---|---|
| 27 Dec 2025 | 72 % / 72 % | 100 % | 31 % / 31 % |
| 31 Jan 2026 | 82 % / 82 % | 46 % | 78 % / 28 % |
| 28 Feb 2026 | 38 % / 37 % | 16 % | 79 % / 10 % |

  The bucket forgets its start within 31 days. **The clock does not:** a short run does not know the
  season has started, so it waits the full 19 days again. **The short run was wrong**, as Fable expected.
- Backtest (same weather): hit 90 %, base 37 % — unchanged, because the backtest already ran from 1 Sep.
- **Not done yet:** the local history starts 12 Oct 2026. Filling 1 Sep to 11 Oct once is about
  **3,400 free calls** (`uv run python -m shroomy.weather.backfill`). Until then the map's memory starts 12 Oct.
  The daily robot on `main` is not changed.

### Steps 5+6: closed out of season, months from Cyprus sources

- **Months a profile does not list now score 0**, and no wait or window runs then (was: halved).
  Edge months (0.3) still score lower but are open. An open window closes when its months end.
- **New months** (full months; edges in the profiles):

| Species | Was | Now | Source |
|---|---|---|---|
| Red pine mushroom | Oct-Jan | Oct-Feb | LOI16; records Oct-Apr |
| Slippery Jack | Oct-Jan | Oct-Feb | 33 *Suillus* records, peak Dec-Jan |
| Bloody milk cap | Sep-Oct | Sep-Nov | WIK-LS |
| Morels | Mar-Apr | Feb-Apr | GBIF Feb 2, Mar 13, Apr 24; LOI16 |
| Desert truffle | Mar-Apr | Feb-Mar (Jan, Apr edges) | LOI16 finds 12 Feb - 21 Mar |
| Wood blewit | Oct-Jan | Nov-Feb | GBIF Jan, Feb |
| Shaggy ink cap | Dec-Feb | Nov-Apr | PIO08; records Nov-Apr |
| Field mushroom | Dec-Mar | Oct-Mar | PIO08 |

- `config/species.yaml` months and the panel's season text were changed to match.
- The site texts that said "never to zero" now say the score is zero further out (panel, tooltip, About).
- **Backtest (same weather):** hit 90 %, base 37 % (species-level, unchanged). Bloody milk cap: 0 % open in
  February (was 19 %). Morels: 0 % in December (was 25 %). Desert truffle: 0 % in December (was 46 %).
- **Genus-only *Russula* finds on 8 and 25 Dec now miss:** white brittlegill stays Sep-Oct (PIO08, kept).
  Those two finds are not named to species, so they may be another *Russula*.
- **Not changed, waiting for Real:** the slippery Jack name, the bronze bolete "rare" tag, hiding the chanterelle,
  the bloody milk cap habitat (a question for the Cyprus Mycological Association).

### Step 8: morels with recent fires and unburned ground

- **EFFIS answered** (it did not this morning): 175 burnt areas in Cyprus, 2016-2026, each with a fire date.
  The **23 July 2025 Limassol fire** is in it (12,437 ha; ERA25 says 120.7 km²).
- Morel habitat = the larger of: **recent burn** (fires in the 2 calendar years before) with full weight from
  50 % burnt [LAR16], or **unburned** Calabrian pine and Troodos broadleaf ground at 0.3 [GUESS, LOI16].
  CORINE 2018 burns are no longer used when the EFFIS layer is there.
- Tree partners lose squares burnt in the last 5 years [GUESS]: 4,450 squares are at least half burnt.
- **Backtest (same weather):** morel habitat squares 89 → 8,985 (sample). 11 species-level events
  (the Karpas morel find now has habitat 1.5 km away): **hit 91 %, base 35 %, gap +56 %**.
- **Morel check:** 28 Feb 2026 (Karpas): window open within 5 km. 10 Mar 2026 (Paphos district): not in this
  weather file (ends 28 Feb). Neither is in the Limassol fire area, which fits "many Cyprus morels are not fire morels".

### Step 9: desert truffle

- Altitude 0-1,000 m → **0-300 m** (LOI16: finds at 80-180 m). Season Feb-Mar (step 6).
- The card now says the real host plant (*Helianthemum*) is **not mapped**: the map uses rock-rose scrub as a stand-in.
- The card shows **rain since 1 September** (island average) as a plain fact. No threshold in mm: no source gives one.
  Until the history is filled back to 1 September (step 4), it says "since 12 October".
- No dated desert truffle finds in the test seasons, so the backtest cannot check it.

### Step 10: fennel king oyster with real fennel points

- GBIF: 285 giant fennel records in Cyprus. **236 used**: licence CC0, CC BY or CC BY-NC, placed to 1 km or better,
  not a garden plant. 10 datasets, all credited in `config/sources.yaml` (`gbif_fennel`).
- **1,936 squares** are within 500 m of a record and get full weight. Elsewhere fields and grassland keep half weight.
- Backtest (same weather): both fennel king oyster finds (25 Jan, 12 Feb 2026) are still inside open windows.
  **But neither is within 2 km of a fennel record**: they hit through the grassland stand-in.
  Records show where people looked, not everywhere fennel grows.

### Step 11: the bucket against the model's own soil moisture

`uv run python -m shroomy.engine.check_bucket <run file>` compares, on forest squares (every 8th), the bucket fill
with ECMWF soil moisture (top 7 cm) interpolated to the square, observed days only, first week skipped (spin-up).

| Run | Days | Squares | r (level, median) | r (day-to-day change) | Best lag |
|---|---|---|---|---|---|
| `run_2026-11-13` (31 past days) | 25 | 5,521 | 0.85 (p10-p90 0.63-0.95) | 0.79 | 0 days |
| `season_2026-11-13` (from 12 Oct) | 26 | 5,521 | 0.84 (0.64-0.94) | 0.80 | 0 days |

- **They move together**, on the same days. By Fable's rule the 12 bucket guesses are **good enough for now**,
  so they are not tuned. This is only one month of autumn; the full 2025-26 season is checked below.

### Step 12: confidence note for users

- New About section **"How sure is this map?"** (Fable's draft), with the hit numbers from this log.
- Also corrected About lines made wrong by these steps: the mushroom clock (19 days, 2-day re-wet, open while wet),
  soil temperature (now from Open-Meteo), burned areas (EFFIS with fire dates), giant fennel (GBIF records),
  desert truffle host. Checked at 375 px and desktop: no sideways scroll.

### Autumn 2026 on saved weather (12 Oct - 20 Nov, all 1,159 points, no new calls)

`--weather data/processed/weather/season_2026-11-13.npz`, old code (`f455bda`) against new, same file.

- **Only 3 find events** fall in this file, all genus-only *Agaricus* (16, 17, 31 Oct): old 0 of 3 hit, new 1 of 3.
  Too few to score. The species-level autumn finds (red pine ×5 on 1 Oct, white brittlegill 27 Sep)
  are before 12 Oct: they need the September download.
- **What the map says today, 13 Nov 2026** (share of habitat squares with a window open):

| | Red pine | Slippery Jack | Bloody milk cap | Matsutake | Oak boletes | Wood blewit | Shaggy ink cap | Fennel k. o. | Morels, truffle |
|---|---|---|---|---|---|---|---|---|---|
| Old | 0 % | 0 % | 0 % | 0 % | 0 % | 2 % | 0 % | 0 % | 0-1 % |
| New | 67 % | 66 % | 79 % | 80 % | 87 % | 62 % | 29 % | 31 % | 0 % |

- Island rain since 12 Oct: 52 mm. The new clock opened windows about 19 days after the mid-October rain
  and keeps them open while the ground stays wet. Public finds from late October and 3 Nov
  (*Agaricus*, boletes, *Russula*) fit "open now". The old code had them "recovering".
- **Honest note:** once open, a wet autumn stays open on most squares. The map then ranks places
  by habitat, water and warmth more than by the clock.

## Round 2 (audit FEEDBACK-round2.md, V4 + Fable section)

### Fix 1: a late window wakes up when it rains again

- A soaking rain on a late window (factor 0.6) now gives a full window again, counted from that day [LOI19].
- Same Sep-Feb weather: shaggy ink cap 90th percentile in Jan-Feb **60 → 100** after rain days
  (it was stuck at the late factor). Red pine was already at 100. Dry autumn unchanged (no window open Sep-Nov).

### Fix 4 (saved data part): hit rate inside the wet season

The base rate is now also counted **only from the first window near each find** to the end (the wet season).

| Same Sep-Feb 2025-26 weather | Finds | Hit | Base (whole season) | Gap | Base (wet season) | Gap (wet season) |
|---|---|---|---|---|---|---|
| Old V4 (`f455bda`) | 10 | 0 % | 16 % | −16 % | 37 % | −37 % |
| New (round 2, fix 1) | 11 | 91 % | 35 % | +56 % | **99 %** | **−8 %** |

- **Honest reading:** once the wet season starts, some window within 5 km is open on almost every day.
  So inside the wet season the new model is **no better than saying "open" every day**.
  The +56 % mostly separates wet weeks from the dry autumn. What it does get right: nothing in the dry
  autumn, windows from mid-December, no January gap. It cannot yet say **which week** inside winter is best.
- A real test needs weather the clock was not tuned on (downloads A and B, next).

### Fix 2: an out-of-season species is never "the best here"

- The general map picks the best species **that has habitat here and is in season that day**.
  A square with no such species gets **no general score** that day (file value 255): it is not drawn,
  and its panel says "No species in season here on this day".
- Saved 13 Nov data: key-species map 98,612 habitat squares, **93,433 drawn** today, **5,179 not drawn**
  (all species: 94,551 drawn, 13,344 not). Zones and "best zones" use in-season squares only.
- **Real, 2026-11-13: keep them hidden.**

### Fix 3: the panel says when a square has burned

- Each square now carries its latest EFFIS fire year in the last 5 years (at least 5 % burned) and the burnt share.
  The panel shows: "🔥 **Burned in 2021** (55 % of the square). Tree partners are not counted here for 5 years after a fire."
  (Under 50 %: "count less here".) The tooltip says the tree cover number is from 2018, before most fires.
- Odou square (34.897 N, 33.166 E), saved 13 Nov data: key-species map **not drawn, "No species in season here"**
  (only morels and wood blewit have habitat; morels are out of season); all-species map: wood blewit.
- Morels on a 3-5-year-old burn still count as unburned host trees at 0.3: **no source**, tagged, TODO-facts A12.

### Phone note: tapping the island did nothing until zoomed in

- Cause: at island zoom the 250 m squares are too small to be in the map tiles, and the 2 km zones are
  switched off in squares mode, so a tap hit nothing.
- Fix: a tap on the island that hits nothing (zoom under 11.5) zooms in to zoom 12 on that place and then
  opens the square there. Taps on the sea do nothing, as before.
- **Not yet checked by eye:** the app window was hidden during this session, so the map could not render.
  Check on the preview: tap the island once at the start view.
