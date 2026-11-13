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
