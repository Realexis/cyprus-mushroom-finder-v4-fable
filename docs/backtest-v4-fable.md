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
